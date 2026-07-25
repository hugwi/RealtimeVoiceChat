from __future__ import annotations

import asyncio
import json
import unittest

from vocis.livekit_adapter import (
    attach_livekit_agent_session,
    attach_livekit_gateway,
)


class _Participant:
    def __init__(self) -> None:
        self.published: list[tuple[dict[str, object], bool, str]] = []

    async def publish_data(self, raw: str, *, reliable: bool, topic: str) -> None:
        self.published.append((json.loads(raw), reliable, topic))


class _Room:
    def __init__(self) -> None:
        self.local_participant = _Participant()
        self.handlers: dict[str, object] = {}

    def on(self, event: str, callback: object) -> None:
        self.handlers[event] = callback


class _Harness:
    def __init__(self) -> None:
        self.prompts: list[tuple[str, str]] = []

    def set_permission_handler(self, handler: object) -> None:
        self.permission_handler = handler

    async def prompt(self, session_id: str, text: str):
        from vocis.omnigent_backend import BackendEvent

        self.prompts.append((session_id, text))
        yield BackendEvent(kind="text_delta", text="Done.")
        yield BackendEvent(kind="completed")

    async def cancel(self, session_id: str) -> None:
        return None


class LiveKitAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_room_data_is_routed_and_results_use_versioned_topic(self) -> None:
        room = _Room()
        attach_livekit_gateway(room, _Harness())

        callback = room.handlers["data_received"]
        callback(
            type(
                "Packet",
                (),
                {
                    "data": json.dumps(
                        {
                            "v": 1,
                            "type": "voice.turn.final",
                            "voiceSessionId": "voice-1",
                            "turnId": "turn-1",
                            "text": "Do the work.",
                        }
                    ).encode()
                },
            )()
        )
        for _ in range(20):
            if len(room.local_participant.published) == 3:
                break
            await asyncio.sleep(0)

        self.assertEqual(len(room.local_participant.published), 3)
        self.assertTrue(all(item[1] for item in room.local_participant.published))
        self.assertTrue(
            all(item[2] == "voice.events.v1" for item in room.local_participant.published)
        )
        self.assertEqual(room.local_participant.published[-1][0]["type"], "harness.completed")

    async def test_server_side_final_stt_event_dispatches_without_browser_transcript(self) -> None:
        room = _Room()
        harness = _Harness()
        gateway = attach_livekit_gateway(room, harness)
        agent_session = _Room()
        attach_livekit_agent_session(agent_session, gateway, "voice-1")

        callback = agent_session.handlers["user_input_transcribed"]
        callback(type("Transcript", (), {"is_final": False, "transcript": "partial"})())
        callback(type("Transcript", (), {"is_final": True, "transcript": "Exact final text"})())
        for _ in range(20):
            if harness.prompts:
                break
            await asyncio.sleep(0)

        self.assertEqual(harness.prompts, [("voice-1", "Exact final text")])


if __name__ == "__main__":
    unittest.main()
