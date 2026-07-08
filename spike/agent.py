"""LiveKit spike agent: whisper STT + Kokoro TTS + ollama brain.

Run:
  console (local mic/speaker):   python spike/agent.py console
  room (browser via playground): python spike/agent.py dev
"""
import asyncio
import threading
import numpy as np

from livekit import rtc
from livekit.agents import (
    Agent, AgentSession, JobContext, JobProcess, WorkerOptions, cli,
    stt as lkstt, tts as lktts,
)
from livekit.agents.worker import JobExecutorType
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.plugins import openai

WHISPER_MODEL = "base.en"
KOKORO_VOICE = "af_heart"
KOKORO_SR = 24000
OLLAMA_MODEL = "qwen2.5:3b"

# Models loaded once at startup in a background thread; jobs never wait for cold load.
_models_ready = threading.Event()
_whisper_model = None
_kokoro_pipeline = None


def _load_models_background():
    global _whisper_model, _kokoro_pipeline
    import time
    import torch
    from faster_whisper import WhisperModel
    from kokoro import KPipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"
    t0 = time.perf_counter()
    print(f"[agent] loading whisper ({device})...", flush=True)
    _whisper_model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute)
    print(f"[agent] whisper ready ({time.perf_counter()-t0:.1f}s), loading kokoro...", flush=True)
    t1 = time.perf_counter()
    _kokoro_pipeline = KPipeline(lang_code="a")
    print(f"[agent] kokoro ready ({time.perf_counter()-t1:.1f}s)", flush=True)

    # Run dummy inference to trigger CUDA JIT compilation now, not on first real call.
    dummy = np.zeros(16000, dtype=np.float32)
    list(_whisper_model.transcribe(dummy, language="en"))
    dummy_audio = list(_kokoro_pipeline("hi", voice=KOKORO_VOICE))
    print(f"[agent] JIT warmup done ({time.perf_counter()-t0:.1f}s total), models ready", flush=True)
    _models_ready.set()


threading.Thread(target=_load_models_background, daemon=True, name="model-loader").start()


def prewarm(proc: JobProcess):
    """Block until background loader finishes; grab already-loaded model refs."""
    _models_ready.wait()
    proc.userdata["whisper"] = _whisper_model
    proc.userdata["kokoro"] = _kokoro_pipeline


# ---------------- whisper STT ----------------
class WhisperSTT(lkstt.STT):
    def __init__(self, model):
        super().__init__(capabilities=lkstt.STTCapabilities(streaming=False, interim_results=False))
        self._m = model

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


# ---------------- Kokoro TTS ----------------
class KokoroTTS(lktts.TTS):
    def __init__(self, pipeline):
        super().__init__(capabilities=lktts.TTSCapabilities(streaming=False),
                         sample_rate=KOKORO_SR, num_channels=1)
        self._kp = pipeline

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

    # When the user leaves (e.g. disables voice), delete the room so this job's
    # agent leaves AND the room is torn down. LiveKit only auto-dispatches a job
    # on room *creation*, so a lingering empty room would let the user re-join
    # the same room with no fresh agent — silence. Deleting it forces the next
    # connection to create a new room, which dispatches a new job.
    def _on_participant_disconnected(participant: rtc.RemoteParticipant):
        ctx.delete_room()

    ctx.room.on("participant_disconnected", _on_participant_disconnected)

    session = AgentSession(
        stt=WhisperSTT(model=ctx.proc.userdata["whisper"]),
        llm=openai.LLM(model=OLLAMA_MODEL, base_url="http://localhost:11434/v1", api_key="ollama"),
        tts=KokoroTTS(pipeline=ctx.proc.userdata["kokoro"]),
    )
    await session.start(
        agent=Agent(instructions="You are a local voice assistant. Reply in one or two short sentences."),
        room=ctx.room,
    )
    await session.generate_reply(instructions="Greet the user briefly and say the local voice spike is live.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        job_executor_type=JobExecutorType.THREAD,  # share models in-process; no subprocess overhead
        initialize_process_timeout=300,
    ))
