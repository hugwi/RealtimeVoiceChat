"""Voice Gateway UI - API client tests."""

import unittest
from unittest.mock import AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from voice_gateway_ui.core import (
    VoiceGatewayClient,
    ConnectorManifest,
    PlatformConnection,
    VoiceSession,
)


class TestVoiceGatewayClient(unittest.IsolatedAsyncioTestCase):
    async def test_list_connectors(self):
        """Test listing connectors."""
        mock_response = [
            {
                'id': 'omnigent',
                'displayName': 'OmniGent',
                'protocolVersion': '1',
                'capabilities': ['coding', 'voice'],
                'authenticationMethods': ['oauth2'],
                'configuration': {},
            }
        ]

        with patch('httpx.AsyncClient') as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = AsyncMock(
                raise_for_status=lambda: None,
                json=lambda: mock_response,
            )
            MockClient.return_value = mock_instance

            client = VoiceGatewayClient('http://test.api')
            connectors = await client.list_connectors()

            self.assertEqual(len(connectors), 1)
            self.assertEqual(connectors[0].id, 'omnigent')
            self.assertEqual(connectors[0].display_name, 'OmniGent')
            self.assertEqual(connectors[0].protocol_version, '1')

    async def test_list_connections(self):
        """Test listing connections."""
        mock_response = [
            {
                'id': 'remote',
                'connectorId': 'omnigent',
                'displayName': 'Remote',
                'configuration': {'serverUrl': 'https://test.api'},
                'credentialGrantId': 'grant-1',
            }
        ]

        with patch('httpx.AsyncClient') as MockClient:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = AsyncMock(
                raise_for_status=lambda: None,
                json=lambda: mock_response,
            )
            MockClient.return_value = mock_instance

            client = VoiceGatewayClient('http://test.api')
            connections = await client.list_connections()

            self.assertEqual(len(connections), 1)
            self.assertEqual(connections[0].id, 'remote')
            self.assertEqual(connections[0].connector_id, 'omnigent')

    async def test_create_connection(self):
        """Test creating a connection."""
        mock_response = {
            'id': 'remote',
            'connectorId': 'omnigent',
            'displayName': 'Remote',
            'configuration': {'serverUrl': 'https://test.api'},
            'credentialGrantId': 'grant-1',
        }

        with patch('httpx.AsyncClient') as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = AsyncMock(
                raise_for_status=lambda: None,
                json=lambda: mock_response,
            )
            MockClient.return_value = mock_instance

            client = VoiceGatewayClient('http://test.api')
            connection = await client.create_connection(
                connection_id='remote',
                connector_id='omnigent',
                display_name='Remote',
                configuration={'serverUrl': 'https://test.api'},
                credential_grant_id='grant-1',
            )

            self.assertEqual(connection.id, 'remote')
            self.assertEqual(connection.display_name, 'Remote')

    async def test_start_voice_session(self):
        """Test starting a voice session."""
        mock_response = {
            'connectionId': 'remote',
            'agentSessionId': 'conv-123',
            'voiceProfileId': 'default',
            'status': 'active',
        }

        with patch('httpx.AsyncClient') as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = AsyncMock(
                raise_for_status=lambda: None,
                json=lambda: mock_response,
            )
            MockClient.return_value = mock_instance

            client = VoiceGatewayClient('http://test.api')
            session = await client.start_voice_session(
                connection_id='remote',
                agent_session_id='conv-123',
                voice_profile_id='default',
            )

            self.assertEqual(session.connection_id, 'remote')
            self.assertEqual(session.agent_session_id, 'conv-123')
            self.assertEqual(session.status, 'active')


if __name__ == '__main__':
    unittest.main()
