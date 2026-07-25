"""Voice Gateway UI - HTTP client for VoiceGatewayApi."""

import httpx
from .types import (
    ConnectorManifest,
    PlatformConnection,
    VoiceSession,
    VoiceGatewayError,
)


class VoiceGatewayClient:
    """HTTP client for Voice Gateway settings API."""

    def __init__(self, base_url: str, auth_token: str | None = None):
        self._base_url = base_url.rstrip('/')
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {auth_token}' if auth_token else '',
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def list_connectors(self) -> list[ConnectorManifest]:
        """List available Platform Connectors."""
        response = await self._client.get('/api/connectors')
        response.raise_for_status()
        data = response.json()
        return [
            ConnectorManifest(
                id=item['id'],
                display_name=item['displayName'],
                protocol_version=item['protocolVersion'],
                capabilities=frozenset(item['capabilities']),
                authentication_methods=frozenset(item['authenticationMethods']),
                configuration=item['configuration'],
            )
            for item in data
        ]

    async def list_connections(self) -> list[PlatformConnection]:
        """List configured Platform Connections."""
        response = await self._client.get('/api/connections')
        response.raise_for_status()
        data = response.json()
        return [
            PlatformConnection(
                id=item['id'],
                connector_id=item['connectorId'],
                display_name=item['displayName'],
                configuration=item['configuration'],
                credential_grant_id=item.get('credentialGrantId'),
            )
            for item in data
        ]

    async def create_connection(
        self,
        connection_id: str,
        connector_id: str,
        display_name: str,
        configuration: dict,
        credential_grant_id: str | None = None,
    ) -> PlatformConnection:
        """Create a new Platform Connection."""
        response = await self._client.post(
            '/api/connections',
            json={
                'id': connection_id,
                'connectorId': connector_id,
                'displayName': display_name,
                'configuration': configuration,
                'credentialGrantId': credential_grant_id,
            },
        )
        response.raise_for_status()
        data = response.json()
        return PlatformConnection(
            id=data['id'],
            connector_id=data['connectorId'],
            display_name=data['displayName'],
            configuration=data['configuration'],
            credential_grant_id=data.get('credentialGrantId'),
        )

    async def update_connection(
        self, connection_id: str, updates: dict
    ) -> PlatformConnection:
        """Update an existing Platform Connection."""
        response = await self._client.patch(
            f'/api/connections/{connection_id}',
            json=updates,
        )
        response.raise_for_status()
        data = response.json()
        return PlatformConnection(
            id=data['id'],
            connector_id=data['connectorId'],
            display_name=data['displayName'],
            configuration=data['configuration'],
            credential_grant_id=data.get('credentialGrantId'),
        )

    async def delete_connection(self, connection_id: str) -> None:
        """Delete a Platform Connection."""
        response = await self._client.delete(
            f'/api/connections/{connection_id}'
        )
        response.raise_for_status()

    async def start_voice_session(
        self,
        connection_id: str,
        agent_session_id: str | None,
        voice_profile_id: str,
    ) -> VoiceSession:
        """Start a new Voice Session."""
        response = await self._client.post(
            '/api/sessions',
            json={
                'connectionId': connection_id,
                'agentSessionId': agent_session_id,
                'voiceProfileId': voice_profile_id,
            },
        )
        response.raise_for_status()
        data = response.json()
        return VoiceSession(
            connection_id=data['connectionId'],
            agent_session_id=data['agentSessionId'],
            voice_profile_id=data['voiceProfileId'],
            status=data['status'],
        )

    async def end_voice_session(self, session_id: str) -> None:
        """End a Voice Session."""
        response = await self._client.delete(f'/api/sessions/{session_id}')
        response.raise_for_status()
