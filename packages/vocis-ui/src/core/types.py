"""Voice Gateway UI - Shared TypeScript types and API client."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ConnectorManifest:
    """A Platform Connector manifest (static metadata, no credentials)."""

    id: str
    display_name: str
    protocol_version: str
    capabilities: frozenset[str]
    authentication_methods: frozenset[str]
    configuration: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PlatformConnection:
    """A configured Platform Connection (non-secret JSON)."""

    id: str
    connector_id: str
    display_name: str
    configuration: dict[str, Any]
    credential_grant_id: str | None


@dataclass(frozen=True, slots=True)
class VoiceSession:
    """An active Voice Session."""

    connection_id: str
    agent_session_id: str
    voice_profile_id: str
    status: Literal["active", "ended"]


class VoiceGatewayError(Exception):
    """Base error for Voice Gateway API."""

    pass


class ConnectorNotFoundError(VoiceGatewayError):
    """Connector not found."""

    pass


class ConnectionNotFoundError(VoiceGatewayError):
    """Connection not found."""

    pass


class SessionError(VoiceGatewayError):
    """Voice Session error."""

    pass
