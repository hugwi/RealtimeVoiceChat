from __future__ import annotations

import asyncio
import json
import unittest

from vocis.acp_agent import InProcessAcpClient, OmnigentAcpAgent
from vocis.gateway import LiveKitVoiceGateway
from vocis.omnigent_backend import BackendEvent

from tests.fakes import FakeOmnigentBackend


class PermissionTest(unittest.IsolatedAsyncioTestCase):
    async def test_permission_waits_for_explicit_livekit_response(self) -> None:
        backend = FakeOmnigentBackend(
            [
                BackendEvent(
                    kind="permission",
                    request_id="elicit-1",
                    title="Allow running the migration?",
                    target_session_id="conv_child",
                ),
                BackendEvent(kind="text_delta", text="Migration completed."),
                BackendEvent(kind="completed"),
            ]
        )
        acp = InProcessAcpClient(OmnigentAcpAgent(backend))
        await acp.load_session("voice-session-1", "conv_target")
        published: list[dict[str, object]] = []
        gateway = LiveKitVoiceGateway(acp, published.append)

        prompt_task = asyncio.create_task(
            gateway.handle_data(
                json.dumps(
                    {
                        "v": 1,
                        "type": "voice.turn.final",
                        "voiceSessionId": "voice-session-1",
                        "turnId": "turn-1",
                        "text": "Run the migration.",
                    }
                ).encode()
            )
        )

        for _ in range(20):
            if any(e["type"] == "harness.permission.requested" for e in published):
                break
            await asyncio.sleep(0)

        self.assertEqual(backend.resolved, [])
        permission = next(
            e for e in published if e["type"] == "harness.permission.requested"
        )
        self.assertEqual(permission["requestId"], "elicit-1")

        await gateway.handle_data(
            json.dumps(
                {
                    "v": 1,
                    "type": "harness.permission.respond",
                    "voiceSessionId": "voice-session-1",
                    "turnId": "turn-1",
                    "requestId": "elicit-1",
                    "decision": "allow",
                }
            ).encode()
        )
        await prompt_task

        self.assertEqual(
            backend.resolved,
            [("conv_child", "elicit-1", "allow")],
        )
        self.assertEqual(published[-1]["type"], "harness.completed")


if __name__ == "__main__":
    unittest.main()
