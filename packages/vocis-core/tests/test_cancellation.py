from __future__ import annotations

import json
import unittest

from vocis.acp_agent import InProcessAcpClient, OmnigentAcpAgent
from vocis.gateway import LiveKitVoiceGateway
from vocis.omnigent_backend import BackendEvent

from tests.fakes import FakeOmnigentBackend


class CancellationTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_interrupts_only_the_mapped_omnigent_session(self) -> None:
        backend = FakeOmnigentBackend()
        acp = InProcessAcpClient(OmnigentAcpAgent(backend))
        await acp.load_session("voice-a", "conv_a")
        await acp.load_session("voice-b", "conv_b")
        published: list[dict[str, object]] = []
        gateway = LiveKitVoiceGateway(acp, published.append)

        await gateway.handle_data(
            json.dumps(
                {
                    "v": 1,
                    "type": "voice.turn.cancel",
                    "voiceSessionId": "voice-b",
                    "turnId": "turn-b",
                }
            ).encode()
        )

        self.assertEqual(backend.cancelled, ["conv_b"])
        self.assertEqual(published[0]["type"], "harness.cancelled")
        self.assertEqual(published[0]["voiceSessionId"], "voice-b")

    async def test_backend_cancellation_is_not_reported_as_success(self) -> None:
        backend = FakeOmnigentBackend([BackendEvent(kind="cancelled")])
        acp = InProcessAcpClient(OmnigentAcpAgent(backend))
        await acp.load_session("voice-a", "conv_a")
        published: list[dict[str, object]] = []
        gateway = LiveKitVoiceGateway(acp, published.append)

        await gateway.handle_data(
            json.dumps(
                {
                    "v": 1,
                    "type": "voice.turn.final",
                    "voiceSessionId": "voice-a",
                    "turnId": "turn-a",
                    "text": "Start then stop.",
                }
            ).encode()
        )

        self.assertEqual(published[-1]["type"], "harness.cancelled")

    async def test_backend_failure_is_reported_with_its_message(self) -> None:
        backend = FakeOmnigentBackend(
            [BackendEvent(kind="failed", text="OmniGent disconnected")]
        )
        acp = InProcessAcpClient(OmnigentAcpAgent(backend))
        await acp.load_session("voice-a", "conv_a")
        published: list[dict[str, object]] = []
        gateway = LiveKitVoiceGateway(acp, published.append)

        await gateway.handle_data(
            json.dumps(
                {
                    "v": 1,
                    "type": "voice.turn.final",
                    "voiceSessionId": "voice-a",
                    "turnId": "turn-a",
                    "text": "Inspect the repository.",
                }
            ).encode()
        )

        self.assertEqual(published[-1]["type"], "harness.failed")
        self.assertEqual(published[-1]["message"], "OmniGent disconnected")


if __name__ == "__main__":
    unittest.main()
