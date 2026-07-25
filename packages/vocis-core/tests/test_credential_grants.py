import asyncio
import json
import unittest
from collections import deque
from typing import Mapping

from vocis.credentials import (
    CredentialGrantDenied,
    CredentialGrantExpired,
    HttpResponse,
    HttpxTransport,
    InMemorySecretStore,
    KeyringSecretStore,
    OmnigentCredentialResolver,
)


class ScriptedTransport:
    def __init__(self, *responses: HttpResponse) -> None:
        self.responses = deque(responses)
        self.requests: list[tuple[str, str, Mapping[str, str]]] = []

    async def post_json(self, url, body, headers):
        self.requests.append(("json", url, body))
        return self.responses.popleft()

    async def post_form(self, url, body, headers):
        self.requests.append(("form", url, body))
        return self.responses.popleft()


class CredentialGrantTests(unittest.IsolatedAsyncioTestCase):
    async def test_device_authorization_acquires_and_resolves_token(self) -> None:
        clock = [100.0]
        transport = ScriptedTransport(
            HttpResponse(
                200,
                {
                    "device_code": "secret-device-code",
                    "user_code": "ABCD-EFGH",
                    "verification_uri_complete": "https://agent.test/oauth/device?user_code=ABCD-EFGH",
                    "expires_in": 600,
                    "interval": 5,
                },
            ),
            HttpResponse(400, {"error": "authorization_pending"}),
            HttpResponse(
                200,
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                },
            ),
        )
        store = InMemorySecretStore()
        resolver = OmnigentCredentialResolver(
            transport, store, clock=lambda: clock[0]
        )

        pending = await resolver.begin(
            "grant-1",
            server_url="https://agent.test/",
            client_id="omnigent-voice",
        )
        self.assertEqual(pending.user_code, "ABCD-EFGH")
        self.assertFalse(await resolver.poll("grant-1"))
        self.assertTrue(await resolver.poll("grant-1"))
        self.assertEqual(
            await resolver.resolve("grant-1"), "access-1"
        )
        self.assertNotIn(
            "secret-device-code", repr(await store.get("grant-1"))
        )

    async def test_expired_access_is_refreshed_once_and_rotated(self) -> None:
        clock = [100.0]
        transport = ScriptedTransport(
            HttpResponse(
                200,
                {
                    "access_token": "access-2",
                    "refresh_token": "refresh-2",
                    "expires_in": 3600,
                },
            )
        )
        store = InMemorySecretStore()
        from vocis.credentials import StoredCredential

        await store.put("grant-1", StoredCredential("old", "refresh-1", 99.0))
        resolver = OmnigentCredentialResolver(
            transport, store, clock=lambda: clock[0]
        )

        tokens = await asyncio.gather(
            resolver.resolve("grant-1", server_url="https://agent.test"),
            resolver.resolve("grant-1", server_url="https://agent.test"),
        )

        self.assertEqual(tokens, ["access-2", "access-2"])
        self.assertEqual(len(transport.requests), 1)
        stored = await store.get("grant-1")
        self.assertEqual(stored.refresh_token, "refresh-2")

    async def test_failed_refresh_clears_local_secret(self) -> None:
        from vocis.credentials import StoredCredential

        store = InMemorySecretStore()
        await store.put("grant-1", StoredCredential("old", "refresh-1", 0))
        resolver = OmnigentCredentialResolver(
            ScriptedTransport(HttpResponse(400, {"error": "expired_token"})),
            store,
            clock=lambda: 100,
        )

        with self.assertRaises(CredentialGrantExpired):
            await resolver.resolve(
                "grant-1", server_url="https://agent.test"
            )
        self.assertIsNone(await store.get("grant-1"))

    async def test_revoke_is_best_effort_and_always_deletes_secret(self) -> None:
        from vocis.credentials import StoredCredential

        store = InMemorySecretStore()
        await store.put("grant-1", StoredCredential("access", "refresh", 999))
        transport = ScriptedTransport(HttpResponse(200, {"revoked": True}))
        resolver = OmnigentCredentialResolver(transport, store)

        await resolver.revoke(
            "grant-1", server_url="https://agent.test"
        )

        self.assertIsNone(await store.get("grant-1"))
        self.assertEqual(
            transport.requests[0][1], "https://agent.test/oauth/revoke"
        )

    async def test_invalid_grant_is_denied_and_deleted(self) -> None:
        from vocis.credentials import StoredCredential

        store = InMemorySecretStore()
        await store.put("grant-1", StoredCredential("access", "stale", 0))
        resolver = OmnigentCredentialResolver(
            ScriptedTransport(HttpResponse(400, {"error": "invalid_grant"})),
            store,
            clock=lambda: 100,
        )

        with self.assertRaises(CredentialGrantDenied):
            await resolver.resolve(
                "grant-1", server_url="https://agent.test"
            )
        self.assertIsNone(await store.get("grant-1"))

    async def test_keyring_store_persists_rotating_secret_outside_connection_json(
        self,
    ) -> None:
        from vocis.credentials import StoredCredential

        class FakeKeyring:
            values = {}

            @classmethod
            def get_password(cls, service, grant_id):
                return cls.values.get((service, grant_id))

            @classmethod
            def set_password(cls, service, grant_id, value):
                cls.values[(service, grant_id)] = value

            @classmethod
            def delete_password(cls, service, grant_id):
                del cls.values[(service, grant_id)]

        store = KeyringSecretStore(backend=FakeKeyring)
        await store.put("grant-1", StoredCredential("access", "refresh", 123.0))

        stored = await store.get("grant-1")
        self.assertEqual(stored.refresh_token, "refresh")
        raw = FakeKeyring.values[("voice-gateway", "grant-1")]
        self.assertEqual(json.loads(raw)["access_token"], "access")

        await store.delete("grant-1")
        self.assertIsNone(await store.get("grant-1"))

    async def test_httpx_transport_uses_json_and_form_requests(self) -> None:
        class Response:
            status_code = 200

            def json(self):
                return {"ok": True}

        class Client:
            def __init__(self):
                self.calls = []

            async def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return Response()

        client = Client()
        transport = HttpxTransport(client)
        await transport.post_json("https://agent.test/json", {"a": "b"}, {})
        await transport.post_form("https://agent.test/form", {"c": "d"}, {})

        self.assertEqual(client.calls[0][1]["json"], {"a": "b"})
        self.assertEqual(client.calls[1][1]["data"], {"c": "d"})


if __name__ == "__main__":
    unittest.main()
