from __future__ import annotations

import unittest
from types import SimpleNamespace

from vocis.acp_sdk_agent import OfficialSdkAttachedSessionAgent
from vocis.omnigent_backend import BackendEvent


class _AttachedSession:
    def __init__(self) -> None:
        self.prompts = []
        self.cancelled = []

    def set_permission_handler(self, handler) -> None:
        self.permission_handler = handler

    async def prompt(self, session_id, text):
        self.prompts.append((session_id, text))
        yield BackendEvent(kind="text_delta", text="hello")
        yield BackendEvent(kind="completed")

    async def cancel(self, session_id):
        self.cancelled.append(session_id)


class AttachedSessionAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_prompt_events_and_cancellation(self) -> None:
        session = _AttachedSession()
        agent = OfficialSdkAttachedSessionAgent(session, "session-1")
        connection = unittest.mock.Mock()
        connection.session_update = unittest.mock.AsyncMock()
        agent.on_connect(connection)

        response = await agent.prompt(
            "session-1",
            [SimpleNamespace(type="text", text="hi")],
        )
        await agent.cancel("session-1")

        self.assertEqual(session.prompts, [("session-1", "hi")])
        self.assertEqual(session.cancelled, ["session-1"])
        self.assertEqual(str(response.stop_reason), "end_turn")
        connection.session_update.assert_awaited_once()

    async def test_rejects_a_different_session_id(self) -> None:
        agent = OfficialSdkAttachedSessionAgent(_AttachedSession(), "session-1")

        with self.assertRaisesRegex(ValueError, "session-1"):
            await agent.load_session("/tmp", "other")


if __name__ == "__main__":
    unittest.main()
