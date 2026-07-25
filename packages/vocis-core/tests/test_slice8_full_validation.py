from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from vocis.connections import PlatformConnectionStore
from vocis.connectors import ConnectorRegistry
from vocis.credentials import (
    HttpResponse,
    InMemorySecretStore,
    OmnigentCredentialResolver,
)
from vocis.execution import (
    ConnectionExecutionError,
    PlatformConnectionExecutor,
)
from vocis.lifecycles import RenewableCredentialProvider
from vocis.settings_api import VoiceGatewayApi


class _AuthorizationServer:
    def __init__(self) -> None:
        self.revoked = False
        self.refreshes = 0

    async def post_json(self, url, body, headers):
        return HttpResponse(
            200,
            {
                "device_code": "device-1",
                "verification_uri_complete": "https://agent.test/approve?code=ABCD",
                "user_code": "ABCD",
                "expires_in": 600,
                "interval": 1,
            },
        )

    async def post_form(self, url, body, headers):
        if url.endswith("/oauth/revoke"):
            self.revoked = True
            return HttpResponse(200, {})
        if body["grant_type"].endswith("device_code"):
            return HttpResponse(
                200,
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                },
            )
        self.refreshes += 1
        return HttpResponse(
            200,
            {
                "access_token": "access-2",
                "refresh_token": "refresh-2",
                "expires_in": 3600,
            },
        )


class _AgentSession:
    def __init__(self, client: httpx.AsyncClient, session_id: str) -> None:
        self._client = client
        self.id = session_id

    async def prompt(self, text: str) -> str:
        response = await self._client.post(
            f"https://agent.test/sessions/{self.id}/turns",
            json={"text": text},
        )
        response.raise_for_status()
        return response.json()["text"]


class _AgentPlatform:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover_sessions(self):
        raise AssertionError("the attach-only connector must not discover sessions")

    async def attach_session(self, session_id: str):
        response = await self._client.get(
            f"https://agent.test/sessions/{session_id}"
        )
        response.raise_for_status()
        return _AgentSession(self._client, session_id)


class _Lifecycle:
    connector_id = "omnigent"

    def __init__(self, handler) -> None:
        self._handler = handler

    @asynccontextmanager
    async def connect(self, *, connection, credential):
        async with httpx.AsyncClient(
            auth=credential,
            transport=httpx.MockTransport(self._handler),
        ) as client:
            yield _AgentPlatform(client)


class Slice8FullValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_connection_runs_and_revocation_fails_closed(self) -> None:
        authorization_server = _AuthorizationServer()
        secrets = InMemorySecretStore()
        resolver = OmnigentCredentialResolver(
            authorization_server,
            secrets,
            clock=lambda: 100,
        )
        authorization = await resolver.begin(
            "grant-1",
            server_url="https://agent.test",
            client_id="voice-gateway",
        )
        self.assertEqual(authorization.user_code, "ABCD")
        self.assertTrue(await resolver.poll("grant-1"))

        seen_authorizations = []

        async def agent_platform(request):
            authorization_header = request.headers["Authorization"]
            seen_authorizations.append(authorization_header)
            if authorization_header == "Bearer access-1":
                return httpx.Response(401)
            if request.method == "GET":
                return httpx.Response(200, json={"id": "conv-1"})
            return httpx.Response(200, json={"text": "VOICE_GATEWAY_OK"})

        with tempfile.TemporaryDirectory() as directory:
            connectors = ConnectorRegistry.discover()
            connection_path = Path(directory) / "connections.json"
            connections = PlatformConnectionStore(connection_path, connectors)
            connections.create(
                connection_id="remote",
                connector_id="omnigent",
                display_name="Remote",
                configuration={"serverUrl": "https://agent.test"},
                credential_grant_id="grant-1",
            )
            lifecycle = _Lifecycle(agent_platform)
            executor = PlatformConnectionExecutor(
                connections,
                connectors,
                type(
                    "Lifecycles",
                    (),
                    {"require": lambda self, connector_id: lifecycle},
                )(),
                RenewableCredentialProvider(resolver),
            )
            api = VoiceGatewayApi(connectors, connections, executor)

            async with api.start_voice_session(
                connection_id="remote",
                agent_session_id="conv-1",
                voice_profile_id="profile-1",
            ) as voice_session:
                result = await voice_session.agent_session.prompt(
                    "Reply with exactly VOICE_GATEWAY_OK"
                )

            self.assertEqual(result, "VOICE_GATEWAY_OK")
            self.assertEqual(
                seen_authorizations,
                [
                    "Bearer access-1",
                    "Bearer access-2",
                    "Bearer access-2",
                ],
            )
            self.assertEqual(authorization_server.refreshes, 1)
            serialized_connection = json.loads(
                connection_path.read_text(encoding="utf-8")
            )
            self.assertNotIn(
                "access-",
                json.dumps(serialized_connection),
            )
            self.assertNotIn(
                "refresh-",
                json.dumps(serialized_connection),
            )

            restarted_resolver = OmnigentCredentialResolver(
                authorization_server,
                secrets,
                clock=lambda: 100,
            )
            restarted_executor = PlatformConnectionExecutor(
                connections,
                connectors,
                type(
                    "Lifecycles",
                    (),
                    {"require": lambda self, connector_id: lifecycle},
                )(),
                RenewableCredentialProvider(restarted_resolver),
            )
            restarted_api = VoiceGatewayApi(
                connectors,
                connections,
                restarted_executor,
            )
            async with restarted_api.start_voice_session(
                connection_id="remote",
                agent_session_id="conv-1",
                voice_profile_id="profile-1",
            ) as voice_session:
                self.assertEqual(
                    await voice_session.agent_session.prompt("after restart"),
                    "VOICE_GATEWAY_OK",
                )
            self.assertEqual(
                seen_authorizations[-2:],
                ["Bearer access-2", "Bearer access-2"],
            )
            self.assertEqual(authorization_server.refreshes, 1)

            await restarted_resolver.revoke(
                "grant-1", server_url="https://agent.test"
            )
            self.assertTrue(authorization_server.revoked)
            self.assertIsNone(await secrets.get("grant-1"))

            post_revoke_resolver = OmnigentCredentialResolver(
                authorization_server,
                secrets,
                clock=lambda: 100,
            )
            post_revoke_executor = PlatformConnectionExecutor(
                connections,
                connectors,
                type(
                    "Lifecycles",
                    (),
                    {"require": lambda self, connector_id: lifecycle},
                )(),
                RenewableCredentialProvider(post_revoke_resolver),
            )
            with self.assertRaisesRegex(
                ConnectionExecutionError, "is not authorized"
            ):
                async with post_revoke_executor.execute(
                    "remote",
                    "conv-1",
                ):
                    pass


if __name__ == "__main__":
    unittest.main()
