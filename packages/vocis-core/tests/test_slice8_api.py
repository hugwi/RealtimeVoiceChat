from __future__ import annotations

import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from vocis.connections import PlatformConnectionStore
from vocis.connectors import ConnectorRegistry
from vocis.settings_api import VoiceGatewayApi


class _Executor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.calls = []
        self.closed = False

    @asynccontextmanager
    async def execute(self, connection_id, agent_session_id):
        self.calls.append((connection_id, agent_session_id))
        try:
            yield SimpleNamespace(
                connection=self.connection,
                agent_session_id=agent_session_id,
                session=SimpleNamespace(id=agent_session_id),
            )
        finally:
            self.closed = True


class Slice8ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_and_voice_session_use_only_public_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            connectors = ConnectorRegistry.discover()
            connections = PlatformConnectionStore(
                Path(directory) / "connections.json", connectors
            )
            connection = connections.create(
                connection_id="remote",
                connector_id="omnigent",
                display_name="Remote",
                configuration={"serverUrl": "https://agent.example.test"},
                credential_grant_id="grant-1",
            )
            executor = _Executor(connection)
            api = VoiceGatewayApi(connectors, connections, executor)

            self.assertEqual(api.list_connections()[0]["id"], "remote")
            self.assertIn("omnigent", {item["id"] for item in api.list_connectors()})
            async with api.start_voice_session(
                connection_id="remote",
                agent_session_id="conv-1",
                voice_profile_id="profile-1",
            ) as session:
                self.assertEqual(
                    (
                        session.connection_id,
                        session.agent_session_id,
                        session.voice_profile_id,
                    ),
                    ("remote", "conv-1", "profile-1"),
                )
                self.assertFalse(executor.closed)

            self.assertEqual(executor.calls, [("remote", "conv-1")])
            self.assertTrue(executor.closed)


if __name__ == "__main__":
    unittest.main()
