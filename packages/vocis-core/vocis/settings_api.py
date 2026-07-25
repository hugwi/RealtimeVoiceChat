"""Host-neutral settings and Voice Session service contract."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from .connections import PlatformConnectionStore
from .connectors import ConnectorRegistry
from .execution import PlatformConnectionExecutor


@dataclass(frozen=True, slots=True)
class VoiceSession:
    connection_id: str
    agent_session_id: str
    voice_profile_id: str
    agent_session: Any


class VoiceGatewayApi:
    """Reusable application seam; web hosts may map these methods to HTTP."""

    def __init__(
        self,
        connectors: ConnectorRegistry,
        connections: PlatformConnectionStore,
        executor: PlatformConnectionExecutor,
    ) -> None:
        self._connectors = connectors
        self._connections = connections
        self._executor = executor

    def list_connectors(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "id": item.id,
                "displayName": item.display_name,
                "capabilities": sorted(item.capabilities),
                "authenticationMethods": list(item.authentication_methods),
                "configuration": dict(item.configuration),
            }
            for item in self._connectors.list()
        )

    def list_connections(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "id": item.id,
                "connectorId": item.connector_id,
                "displayName": item.display_name,
                "configuration": dict(item.configuration),
                "credentialGrantId": item.credential_grant_id,
            }
            for item in self._connections.list()
        )

    @asynccontextmanager
    async def start_voice_session(
        self,
        *,
        connection_id: str,
        agent_session_id: str | None,
        voice_profile_id: str,
    ) -> AsyncIterator[VoiceSession]:
        if not isinstance(voice_profile_id, str) or not voice_profile_id.strip():
            raise ValueError("Voice Profile id must be a non-empty string")
        async with self._executor.execute(
            connection_id, agent_session_id
        ) as execution:
            yield VoiceSession(
                connection_id=execution.connection.id,
                agent_session_id=execution.agent_session_id,
                voice_profile_id=voice_profile_id.strip(),
                agent_session=execution.session,
            )


__all__ = ["VoiceGatewayApi", "VoiceSession"]
