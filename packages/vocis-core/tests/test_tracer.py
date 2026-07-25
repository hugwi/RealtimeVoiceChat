from __future__ import annotations

import json
import unittest

from vocis.acp_agent import InProcessAcpClient, OmnigentAcpAgent
from vocis.gateway import LiveKitVoiceGateway
from vocis.omnigent_backend import BackendEvent

from tests.fakes import FakeOmnigentBackend


class TranscriptTracerTest(unittest.IsolatedAsyncioTestCase):
    async def test_final_transcript_reaches_omnigent_and_streams_back(self) -> None:
        backend = FakeOmnigentBackend(
            [
                BackendEvent(kind="text_delta", text="I found the problem. "),
                BackendEvent(kind="text_delta", text="The tests pass."),
                BackendEvent(kind="completed"),
            ]
        )
        agent = OmnigentAcpAgent(backend)
        acp = InProcessAcpClient(agent)
        await acp.initialize()
        await acp.load_session("voice-session-1", "conv_target")

        published: list[dict[str, object]] = []
        gateway = LiveKitVoiceGateway(acp, published.append)

        await gateway.handle_data(
            json.dumps(
                {
                    "v": 1,
                    "type": "voice.turn.final",
                    "voiceSessionId": "voice-session-1",
                    "turnId": "turn-1",
                    "text": "Fix the authentication bug and run tests.",
                }
            ).encode()
        )

        self.assertEqual(
            backend.sent,
            [("conv_target", "Fix the authentication bug and run tests.")],
        )
        self.assertEqual(
            published,
            [
                {
                    "v": 1,
                    "type": "voice.turn.accepted",
                    "voiceSessionId": "voice-session-1",
                    "turnId": "turn-1",
                },
                {
                    "v": 1,
                    "type": "harness.text.delta",
                    "voiceSessionId": "voice-session-1",
                    "turnId": "turn-1",
                    "text": "I found the problem. ",
                },
                {
                    "v": 1,
                    "type": "harness.text.delta",
                    "voiceSessionId": "voice-session-1",
                    "turnId": "turn-1",
                    "text": "The tests pass.",
                },
                {
                    "v": 1,
                    "type": "harness.completed",
                    "voiceSessionId": "voice-session-1",
                    "turnId": "turn-1",
                    "text": "I found the problem. The tests pass.",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
