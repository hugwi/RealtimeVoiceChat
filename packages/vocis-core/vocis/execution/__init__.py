"""Platform-neutral execution of a configured Platform Connection."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from .connections import PlatformConnection, PlatformConnectionStore
from .connectors import ConnectorManifest, ConnectorManifestError, ConnectorRegistry


class ConnectionExecutionError(RuntimeError):
    """A Platform Connection cannot be activated honestly."""


class CredentialResolver(Protocol):
    async def resolve(
        self, grant_id: str, *, server_url: str | None = None
    ) -> Any: ...


class ConnectedPlatform(Protocol):
    async def discover_sessions(self) -> Sequence[str]: ...

    async def attach_session(self, session_id: str) -> Any: ...


class ConnectorLifecycle(Protocol):
    connector_id: str

    def connect(
        self,
        *,
        connection: PlatformConnection,
        credential: str | None,
    ) -> Any:
        """Return an async context manager yielding a ConnectedPlatform."""


class ConnectorLifecycleRegistry(Protocol):
    def require(self, connector_id: str) -> ConnectorLifecycle: ...


@dataclass(frozen=True, slots=True)
class ConnectionExecution:
    """Live Agent Session handle consumed by the Voice Gateway."""

    connection: PlatformConnection
    manifest: ConnectorManifest
    agent_session_id: str
    session: Any


class PlatformConnectionExecutor:
    """Select, authenticate, activate, and attach a Platform Connection."""

    def __init__(
        self,
        connections: PlatformConnectionStore,
        manifests: ConnectorRegistry,
        lifecycles: ConnectorLifecycleRegistry,
        credentials: CredentialResolver | None = None,
    ) -> None:
        self._connections = connections
        self._manifests = manifests
        self._lifecycles = lifecycles
        self._credentials = credentials

    @asynccontextmanager
    async def execute(
        self, connection_id: str, agent_session_id: str | None = None
    ) -> AsyncIterator[ConnectionExecution]:
        connection = self._connections.get(connection_id)
        try:
            manifest = self._manifests.require(connection.connector_id)
            lifecycle = self._lifecycles.require(connection.connector_id)
        except (ConnectorManifestError, KeyError, LookupError) as exc:
            raise ConnectionExecutionError(str(exc)) from exc
        if lifecycle.connector_id != manifest.id:
            raise ConnectionExecutionError(
                f"connector lifecycle {lifecycle.connector_id!r} cannot execute "
                f"manifest {manifest.id!r}"
            )

        credential = await self._resolve_credential(connection)
        try:
            context = lifecycle.connect(
                connection=connection,
                credential=credential,
            )
            async with context as platform:
                session_id = await self._select_session(
                    platform, manifest, connection.configuration, agent_session_id
                )
                session = await platform.attach_session(session_id)
                if session is None:
                    raise ConnectionExecutionError(
                        f"connector {manifest.id!r} returned no Agent Session "
                        f"for {session_id!r}"
                    )
                yield ConnectionExecution(
                    connection=connection,
                    manifest=manifest,
                    agent_session_id=session_id,
                    session=session,
                )
        except ConnectionExecutionError:
            raise
        except Exception as exc:
            raise ConnectionExecutionError(
                f"cannot execute Platform Connection {connection.id!r}: {exc}"
            ) from exc

    async def _resolve_credential(
        self, connection: PlatformConnection
    ) -> Any:
        grant_id = connection.credential_grant_id
        if grant_id is None:
            return None
        if self._credentials is None:
            raise ConnectionExecutionError(
                f"Platform Connection {connection.id!r} requires Credential "
                f"Grant {grant_id!r}, but no resolver is configured"
            )
        server_url = connection.configuration.get("serverUrl")
        try:
            return await self._credentials.resolve(
                grant_id,
                server_url=server_url if isinstance(server_url, str) else None,
            )
        except Exception as exc:
            raise ConnectionExecutionError(
                f"cannot resolve Credential Grant {grant_id!r}: {exc}"
            ) from exc

    @staticmethod
    async def _select_session(
        platform: ConnectedPlatform,
        manifest: ConnectorManifest,
        configuration: Mapping[str, Any],
        requested_id: str | None,
    ) -> str:
        if requested_id is not None:
            return _session_id(requested_id)

        configured_id = configuration.get("sessionId")
        if configured_id is not None:
            return _session_id(configured_id)

        if not manifest.supports("sessionDiscovery"):
            raise ConnectionExecutionError(
                f"connector {manifest.id!r} cannot discover Agent Sessions; "
                "an Agent Session id is required"
            )
        try:
            discovered = tuple(await platform.discover_sessions())
        except Exception as exc:
            raise ConnectionExecutionError(
                f"connector {manifest.id!r} could not discover Agent Sessions: {exc}"
            ) from exc
        if len(discovered) != 1:
            raise ConnectionExecutionError(
                f"connector {manifest.id!r} discovered {len(discovered)} Agent "
                "Sessions; specify an Agent Session id"
            )
        return _session_id(discovered[0])


def _session_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectionExecutionError(
            "Agent Session id must be a non-empty string"
        )
    return value.strip()


__all__ = [
    "ConnectedPlatform",
    "ConnectionExecution",
    "ConnectionExecutionError",
    "ConnectorLifecycle",
    "ConnectorLifecycleRegistry",
    "CredentialResolver",
    "PlatformConnectionExecutor",
]
