from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

from vocis.connections import PlatformConnection
from vocis.credentials import RenewableBearerAuth
from vocis.lifecycles import (
    BuiltinLifecycleRegistry,
    GenericAcpConnectorLifecycle,
    OmnigentConnectorLifecycle,
    RenewableCredentialProvider,
)


class BuiltinLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def test_registry_contains_both_builtin_connectors(self) -> None:
        registry = BuiltinLifecycleRegistry()

        self.assertIsInstance(
            registry.require("generic-acp"), GenericAcpConnectorLifecycle
        )
        self.assertIsInstance(
            registry.require("omnigent"), OmnigentConnectorLifecycle
        )

    async def test_provider_returns_renewable_auth_without_exposing_token(self) -> None:
        resolver = AsyncMock()
        provider = RenewableCredentialProvider(resolver)

        auth = await provider.resolve(
            "grant-1", server_url="https://agent.example.test"
        )

        self.assertIsInstance(auth, RenewableBearerAuth)
        resolver.resolve.assert_not_called()

    async def test_omnigent_lifecycle_injects_auth_and_closes_backend(self) -> None:
        connection = PlatformConnection(
            id="remote",
            connector_id="omnigent",
            display_name="Remote",
            configuration=MappingProxyType(
                {"serverUrl": "https://agent.example.test"}
            ),
            credential_grant_id="grant-1",
            created_at="now",
            updated_at="now",
        )
        backend = unittest.mock.Mock()
        backend.require_session = AsyncMock()
        backend.close = AsyncMock()
        auth = object()

        with patch(
            "vocis.lifecycles.OmnigentSdkBackend", return_value=backend
        ) as backend_type:
            async with OmnigentConnectorLifecycle().connect(
                connection=connection, credential=auth
            ) as platform:
                session = await platform.attach_session("conv-1")

        backend_type.assert_called_once_with(
            "https://agent.example.test", auth=auth
        )
        backend.require_session.assert_awaited_once_with("conv-1")
        self.assertIsNotNone(session)
        backend.close.assert_awaited_once()

    async def test_generic_acp_lifecycle_spawns_and_attaches_configured_session(
        self,
    ) -> None:
        connection = PlatformConnection(
            id="local",
            connector_id="generic-acp",
            display_name="Local ACP",
            configuration=MappingProxyType(
                {
                    "command": "agent",
                    "arguments": ["--stdio"],
                    "sessionId": "session-1",
                    "workingDirectory": "/project",
                }
            ),
            credential_grant_id=None,
            created_at="now",
            updated_at="now",
        )
        client = object()

        @asynccontextmanager
        async def spawned(*args, **kwargs):
            yield client

        with patch(
            "vocis.lifecycles.spawn_generic_acp_connector",
            side_effect=spawned,
        ) as spawn:
            async with GenericAcpConnectorLifecycle().connect(
                connection=connection, credential=None
            ) as platform:
                self.assertIs(await platform.attach_session("session-1"), client)

        spawn.assert_called_once_with(
            "agent",
            ("--stdio",),
            session_id="session-1",
            cwd="/project",
        )


if __name__ == "__main__":
    unittest.main()
