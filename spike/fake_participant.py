"""Automated room test: publish a speech wav into a LiveKit room, record the
agent's spoken reply back. Proves the full room round-trip with no human mic."""
import asyncio, sys
import numpy as np, soundfile as sf
from livekit import rtc, api

URL = "ws://localhost:7880"
ROOM = "spike"
IN_WAV = "code/reference_audio.wav"
OUT_WAV = "/tmp/spike_agent_reply.wav"
LISTEN_S = 25.0


async def main():
    token = (api.AccessToken("devkey", "XhtHLb2P1O6vZBy5uuLEegDQFk-Tg6RcTbTZGzXm840")
             .with_identity("tester").with_name("tester")
             .with_grants(api.VideoGrants(room_join=True, room=ROOM)).to_jwt())
    room = rtc.Room()

    captured = []  # int16 mono chunks from agent
    cap_sr = [48000]

    @room.on("track_subscribed")
    def on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"[test] subscribed to agent audio from {participant.identity}")
            asyncio.create_task(_drain(track))

    async def _drain(track):
        stream = rtc.AudioStream(track)
        async for ev in stream:
            f = ev.frame
            cap_sr[0] = f.sample_rate
            captured.append(np.frombuffer(f.data, dtype=np.int16).copy())

    await room.connect(URL, token)
    print("[test] connected to room")

    # load speech, resample to 24000, publish as mic track
    data, sr = sf.read(IN_WAV, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    pub_sr = 24000
    if sr != pub_sr:
        n = int(len(data) * pub_sr / sr)
        data = np.interp(np.linspace(0, len(data), n, endpoint=False),
                         np.arange(len(data)), data).astype(np.float32)
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)

    source = rtc.AudioSource(pub_sr, 1)
    track = rtc.LocalAudioTrack.create_audio_track("mic", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    # let the startup greeting play out first, then reset capture so we only
    # record the reply to our spoken turn
    await asyncio.sleep(10.0)
    captured.clear()
    print("[test] greeting window passed, now speaking user turn")

    # push 20ms frames, then ~1.5s silence to trigger VAD endpoint
    step = pub_sr // 50  # 20ms
    print(f"[test] streaming {len(pcm)/pub_sr:.1f}s of speech...")
    for i in range(0, len(pcm), step):
        chunk = pcm[i:i + step]
        if len(chunk) < step:
            chunk = np.pad(chunk, (0, step - len(chunk)))
        await source.capture_frame(rtc.AudioFrame(chunk.tobytes(), pub_sr, 1, step))
        await asyncio.sleep(0.02)
    sil = np.zeros(step, dtype=np.int16)
    for _ in range(90):  # 1.8s silence
        await source.capture_frame(rtc.AudioFrame(sil.tobytes(), pub_sr, 1, step))
        await asyncio.sleep(0.02)

    print(f"[test] listening {LISTEN_S}s for agent reply...")
    await asyncio.sleep(LISTEN_S)

    if captured:
        au = np.concatenate(captured)
        sf.write(OUT_WAV, au, cap_sr[0])
        print(f"[test] RECORDED agent reply: {len(au)/cap_sr[0]:.2f}s @ {cap_sr[0]}Hz -> {OUT_WAV}")
    else:
        print("[test] NO agent audio captured")
    await room.disconnect()

asyncio.run(main())
