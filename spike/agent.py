"""LiveKit spike agent: whisper STT + Kokoro TTS + silero VAD + ollama brain.

Proves RVC's local models run inside livekit-agents. RVC framework NOT used.
Run:
  console (local mic/speaker):   python spike/agent.py console
  room (browser via playground): python spike/agent.py dev
"""
import asyncio
import numpy as np

from livekit import rtc
from livekit.agents import (
    Agent, AgentSession, JobContext, WorkerOptions, cli,
    stt as lkstt, tts as lktts,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.plugins import openai

WHISPER_MODEL = "base.en"
KOKORO_VOICE = "af_heart"
KOKORO_SR = 24000
OLLAMA_MODEL = "qwen2.5:3b"


# ---------------- whisper STT (non-streaming; framework VAD-segments) ----------------
class WhisperSTT(lkstt.STT):
    def __init__(self):
        super().__init__(capabilities=lkstt.STTCapabilities(streaming=False, interim_results=False))
        from faster_whisper import WhisperModel
        self._m = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")

    async def _recognize_impl(self, buffer, *, language=None, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        frame = rtc.combine_audio_frames(buffer)
        data = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
        sr = frame.sample_rate
        if sr != 16000 and len(data):
            n = int(len(data) * 16000 / sr)
            data = np.interp(np.linspace(0, len(data), n, endpoint=False),
                             np.arange(len(data)), data).astype(np.float32)

        def run():
            segs, _ = self._m.transcribe(data, language="en")
            return "".join(s.text for s in segs).strip()

        text = await asyncio.get_event_loop().run_in_executor(None, run)
        return lkstt.SpeechEvent(
            type=lkstt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[lkstt.SpeechData(language="en", text=text)],
        )


# ---------------- Kokoro TTS (non-streaming chunked) ----------------
class KokoroTTS(lktts.TTS):
    def __init__(self):
        super().__init__(capabilities=lktts.TTSCapabilities(streaming=False),
                         sample_rate=KOKORO_SR, num_channels=1)
        from kokoro import KPipeline
        self._kp = KPipeline(lang_code="a")

    def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        return _KokoroStream(self, text, conn_options)


class _KokoroStream(lktts.ChunkedStream):
    def __init__(self, tts, text, conn_options):
        super().__init__(tts=tts, input_text=text, conn_options=conn_options)
        self._text = text
        self._kp = tts._kp

    async def _run(self, output_emitter):
        output_emitter.initialize(
            request_id="kokoro", sample_rate=KOKORO_SR, num_channels=1,
            mime_type="audio/pcm",
        )

        def synth():
            chunks = [a for _, _, a in self._kp(self._text, voice=KOKORO_VOICE)]
            return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

        audio = await asyncio.get_event_loop().run_in_executor(None, synth)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        output_emitter.push(pcm)
        output_emitter.flush()


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    session = AgentSession(
        stt=WhisperSTT(),
        llm=openai.LLM(model=OLLAMA_MODEL, base_url="http://localhost:11434/v1", api_key="ollama"),
        tts=KokoroTTS(),
    )
    await session.start(
        agent=Agent(instructions="You are a local voice assistant. Reply in one or two short sentences."),
        room=ctx.room,
    )
    await session.generate_reply(instructions="Greet the user briefly and say the local voice spike is live.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
