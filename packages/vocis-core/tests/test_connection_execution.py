from __future__ import annotations

import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from vocis.connections import PlatformConnectionStore
from vocis.connectors import ConnectorRegistry
from vocis.execution import (
    ConnectionExecutionError,
    PlatformConnectionExecutor,
)


class _Credentials:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def resolve(self, grant_id: str, *, server_url: str | None = None) -> str:
        self.calls.append((grant_id, server_url))
        return "access-token"


class _Platform:
    def __init__(self, discovered: tuple[str, ...] = ()) -> None:
        self.discovered = discovered
        self.discovery_calls = 0
        self.attached: list[str] = []

    async def discover_sessions(self) -> tuple[str, ...]:
        self.discovery_calls += 1
        return self.discovered

    async def attach_session(self, session_id: str) -> object:
        self.attached.append(session_id)
        return SimpleNamespace(id=session_id)


class _Lifecycle:
    connector_id = "omnigent"

    def __init__(self, platform: _Platform) -> None:
        self.platform = platform
        self.calls = []
        self.closed = False

    @asynccontextmanager
    async def connect(self, *, connection, credential):
        self.calls.append((connection, credential))
        try:
            yield self.platform
        finally:
            self.closed = True


class _Lifecycles:
    def __init__(self, lifecycle: _Lifecycle) -> None:
        self.lifecycle = lifecycle

    def require(self, connector_id: str) -> _Lifecycle:
        if connector_id != self.lifecycle.connector_id:
            raise KeyError(connector_id)
        return self.lifecycle


class ConnectionExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.manifests = ConnectorRegistry.discover()
        self.connections = PlatformConnectionStore(
            Path(self.temporary_directory.name) / "connections.json",
            self.manifests,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_resolves_grant_and_attaches_explicit_session(self) -> None:
        self.connections.create(
            connection_id="remote",
            connector_id="omnigent",
            display_name="Remote",
            configuration={"serverUrl": "https://agent.example.test"},
            credential_grant_id="grant-1",
        )
        credentials = _Credentials()
        platform = _Platform()
        lifecycle = _Lifecycle(platform)
        executor = PlatformConnectionExecutor(
            self.connections,
            self.manifests,
            _Lifecycles(lifecycle),
            credentials,
        )

        async with executor.execute("remote", "session-1") as execution:
            self.assertEqual(execution.agent_session_id, "session-1")
            self.assertEqual(execution.session.id, "session-1")
            self.assertFalse(lifecycle.closed)

        self.assertEqual(
            credentials.calls,
            [("grant-1", "https://agent.example.test")],
        )
        self.assertEqual(platform.attached, ["session-1"])
        self.assertEqual(platform.discovery_calls, 0)
        self.assertTrue(lifecycle.closed)

    async def test_uses_configured_session_without_discovery(self) -> None:
        self.connections.create(
            connection_id="local",
            connector_id="generic-acp",
            display_name="Local",
            configuration={"command": "agent", "sessionId": "configured"},
        )
        platform = _Platform()
        lifecycle = _Lifecycle(platform)
        lifecycle.connector_id = "generic-acp"
        executor = PlatformConnectionExecutor(
            self.connections, self.manifests, _Lifecycles(lifecycle)
        )

        async with executor.execute("local") as execution:
            self.assertEqual(execution.agent_session_id, "configured")

        self.assertEqual(lifecycle.calls[0][1], None)
        self.assertEqual(platform.discovery_calls, 0)

    async def test_attach_only_connector_requires_session_id(self) -> None:
        self.connections.create(
            connection_id="remote",
            connector_id="omnigent",
            display_name="Remote",
            configuration={"serverUrl": "https://agent.example.test"},
            credential_grant_id="grant-1",
        )
        platform = _Platform(("should-not-be-used",))
        lifecycle = _Lifecycle(platform)
        executor = PlatformConnectionExecutor(
            self.connections,
            self.manifests,
            _Lifecycles(lifecycle),
            _Credentials(),
        )

        with self.assertRaisesRegex(
            ConnectionExecutionError, "cannot discover Agent Sessions"
        ):
            async with executor.execute("remote"):
                self.fail("execution should not start")
        self.assertEqual(platform.discovery_calls, 0)
        self.assertTrue(lifecycle.closed)

    async def test_rejects_lifecycle_for_a_different_connector(self) -> None:
        self.connections.create(
            connection_id="local",
            connector_id="generic-acp",
            display_name="Local",
            configuration={"command": "agent", "sessionId": "configured"},
        )
        lifecycle = _Lifecycle(_Platform())

        with self.assertRaisesRegex(
            ConnectionExecutionError, "cannot execute manifest"
        ):
            async with PlatformConnectionExecutor(
                self.connections,
                self.manifests,
                SimpleNamespace(require=lambda _: lifecycle),
            ).execute("local"):
                self.fail("execution should not start")


if __name__ == "__main__":
    unittest.main()
