from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

import httpx

from vocis.connections import PlatformConnectionStore
from vocis.connectors import ConnectorRegistry
from vocis.credentials import (
    HttpxTransport,
    KeyringSecretStore,
    OmnigentCredentialResolver,
    StoredCredential,
)
from vocis.execution import (
    ConnectionExecutionError,
    PlatformConnectionExecutor,
)
from vocis.lifecycles import (
    BuiltinLifecycleRegistry,
    RenewableCredentialProvider,
)


class LiveCredentialLifecycleSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_authorize_refresh_restart_revoke_and_fail_closed(self) -> None:
        if os.environ.get("VOICE_CREDENTIAL_LIFECYCLE_LIVE") != "1":
            self.skipTest(
                "set VOICE_CREDENTIAL_LIFECYCLE_LIVE=1 to run the live smoke"
            )
        if os.environ.get("VOICE_CREDENTIAL_LIFECYCLE_ALLOW_REVOKE") != "1":
            self.fail(
                "set VOICE_CREDENTIAL_LIFECYCLE_ALLOW_REVOKE=1 to acknowledge "
                "that this test revokes its disposable Credential Grant"
            )

        store_path = self._required_path("VOICE_CONNECTION_STORE")
        connection_id = self._required("OMNIGENT_CONNECTION_ID")
        session_id = self._required("OMNIGENT_SESSION_ID")
        manifests = ConnectorRegistry.discover()
        connections = PlatformConnectionStore(store_path, manifests)
        connection = connections.get(connection_id)
        self.assertEqual(connection.connector_id, "omnigent")
        grant_id = connection.credential_grant_id
        self.assertIsNotNone(grant_id)
        server_url = str(connection.configuration["serverUrl"])
        secrets = KeyringSecretStore()
        clients: list[httpx.AsyncClient] = []
        authorized = False
        revoked = False

        def restarted_resolver() -> OmnigentCredentialResolver:
            client = httpx.AsyncClient()
            clients.append(client)
            return OmnigentCredentialResolver(
                HttpxTransport(client),
                secrets,
                client_secret=os.environ.get("OMNIGENT_CLIENT_SECRET"),
            )

        def executor(resolver) -> PlatformConnectionExecutor:
            return PlatformConnectionExecutor(
                connections,
                manifests,
                BuiltinLifecycleRegistry(),
                RenewableCredentialProvider(resolver),
            )

        resolver = restarted_resolver()
        try:
            pending = await resolver.begin(
                grant_id,
                server_url=server_url,
                client_id=os.environ.get(
                    "VOICE_DEVICE_CLIENT_ID",
                    "omnigent-voice-gateway-live-smoke",
                ),
            )
            print(f"\nApprove the disposable grant at {pending.verification_url}")
            if pending.user_code:
                print(f"Enter code {pending.user_code}")
            while not await resolver.poll(grant_id):
                await asyncio.sleep(pending.poll_interval)
            authorized = True

            async with executor(resolver).execute(connection_id, session_id):
                pass
            credential = await secrets.get(grant_id)
            self.assertIsNotNone(credential)
            await secrets.put(
                grant_id,
                StoredCredential(
                    credential.access_token,
                    credential.refresh_token,
                    0,
                ),
            )

            await clients[-1].aclose()
            resolver = restarted_resolver()
            async with executor(resolver).execute(connection_id, session_id):
                pass
            refreshed = await secrets.get(grant_id)
            self.assertIsNotNone(refreshed)
            self.assertGreater(refreshed.expires_at, 0)

            await clients[-1].aclose()
            resolver = restarted_resolver()
            async with executor(resolver).execute(connection_id, session_id):
                pass

            await resolver.revoke(grant_id, server_url=server_url)
            revoked = True
            await clients[-1].aclose()
            resolver = restarted_resolver()
            with self.assertRaisesRegex(
                ConnectionExecutionError,
                "is not authorized",
            ):
                async with executor(resolver).execute(
                    connection_id,
                    session_id,
                ):
                    pass
        finally:
            if authorized and not revoked:
                await resolver.revoke(grant_id, server_url=server_url)
            for client in clients:
                if not client.is_closed:
                    await client.aclose()

    def _required(self, name: str) -> str:
        value = os.environ.get(name, "").strip()
        self.assertTrue(value, f"{name} is required")
        return value

    def _required_path(self, name: str) -> Path:
        path = Path(self._required(name)).expanduser()
        self.assertTrue(path.is_file(), f"{name} does not exist: {path}")
        return path


if __name__ == "__main__":
    unittest.main()
