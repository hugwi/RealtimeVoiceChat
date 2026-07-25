"""Built-in Platform Connector execution lifecycles."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from .acp_agent import InProcessAcpClient, OmnigentAcpAgent
from .connections import PlatformConnection
from .connectors.generic_acp import spawn_generic_acp_connector
from .credentials import OmnigentCredentialResolver, RenewableBearerAuth
from .omnigent_backend import OmnigentSdkBackend


@dataclass(frozen=True, slots=True)
class RenewableCredentialProvider:
    resolver: OmnigentCredentialResolver

    async def resolve(
        self, grant_id: str, *, server_url: str | None = None
    ) -> RenewableBearerAuth:
        if server_url is None:
            raise ValueError("renewable OmniGent authentication requires serverUrl")
        return RenewableBearerAuth(self.resolver, grant_id, server_url=server_url)


class _OmnigentPlatform:
    def __init__(self, backend: OmnigentSdkBackend) -> None:
        self._backend = backend

    async def discover_sessions(self) -> tuple[str, ...]:
        raise RuntimeError("the OmniGent connector does not advertise session discovery")

    async def attach_session(self, session_id: str) -> InProcessAcpClient:
        agent = OmnigentAcpAgent(self._backend)
        client = InProcessAcpClient(agent)
        await client.load_session(session_id, session_id)
        return client


class OmnigentConnectorLifecycle:
    connector_id = "omnigent"

    @asynccontextmanager
    async def connect(
        self, *, connection: PlatformConnection, credential: Any
    ) -> AsyncIterator[_OmnigentPlatform]:
        server_url = str(connection.configuration["serverUrl"])
        backend = OmnigentSdkBackend(server_url, auth=credential)
        try:
            yield _OmnigentPlatform(backend)
        finally:
            await backend.close()


class _GenericAcpPlatform:
    def __init__(self, client: Any, session_id: str) -> None:
        self._client = client
        self._session_id = session_id

    async def discover_sessions(self) -> tuple[str, ...]:
        raise RuntimeError(
            "the generic ACP connector does not advertise session discovery"
        )

    async def attach_session(self, session_id: str) -> Any:
        if session_id != self._session_id:
            raise ValueError(
                f"generic ACP process is attached to Agent Session "
                f"{self._session_id!r}, not {session_id!r}"
            )
        return self._client


class GenericAcpConnectorLifecycle:
    connector_id = "generic-acp"

    @asynccontextmanager
    async def connect(
        self, *, connection: PlatformConnection, credential: Any
    ) -> AsyncIterator[_GenericAcpPlatform]:
        if credential is not None:
            raise ValueError("the generic ACP connector does not accept credentials")
        configuration = connection.configuration
        session_id = str(configuration["sessionId"])
        async with spawn_generic_acp_connector(
            str(configuration["command"]),
            tuple(configuration.get("arguments", ())),
            session_id=session_id,
            cwd=configuration.get("workingDirectory"),
        ) as client:
            yield _GenericAcpPlatform(client, session_id)


class BuiltinLifecycleRegistry:
    def __init__(self) -> None:
        self._lifecycles = {
            "generic-acp": GenericAcpConnectorLifecycle(),
            "omnigent": OmnigentConnectorLifecycle(),
        }

    def require(self, connector_id: str) -> Any:
        try:
            return self._lifecycles[connector_id]
        except KeyError as exc:
            raise KeyError(
                f"connector {connector_id!r} has no built-in execution lifecycle"
            ) from exc


__all__ = [
    "BuiltinLifecycleRegistry",
    "GenericAcpConnectorLifecycle",
    "OmnigentConnectorLifecycle",
    "RenewableCredentialProvider",
]
