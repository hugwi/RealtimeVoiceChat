import asyncio
import unittest

import httpx

from vocis.credentials import (
    HttpResponse,
    InMemorySecretStore,
    OmnigentCredentialResolver,
    RenewableBearerAuth,
    StoredCredential,
)


class RefreshTransport:
    def __init__(self) -> None:
        self.calls = 0

    async def post_json(self, url, body, headers):
        raise AssertionError("device authorization is not expected")

    async def post_form(self, url, body, headers):
        self.calls += 1
        return HttpResponse(
            200,
            {
                "access_token": "fresh-access",
                "refresh_token": "fresh-refresh",
                "expires_in": 3600,
            },
        )


class RenewableHttpAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = InMemorySecretStore()
        await self.store.put(
            "grant-1",
            StoredCredential("stale-access", "old-refresh", 10_000),
        )
        self.transport = RefreshTransport()
        self.resolver = OmnigentCredentialResolver(
            self.transport,
            self.store,
            clock=lambda: 100,
        )
        self.auth = RenewableBearerAuth(
            self.resolver,
            "grant-1",
            server_url="https://agent.test/",
        )

    async def test_injects_resolved_bearer_token(self) -> None:
        async def handler(request):
            self.assertEqual(
                request.headers["Authorization"], "Bearer stale-access"
            )
            return httpx.Response(200, json={"ok": True})

        async with httpx.AsyncClient(
            auth=self.auth, transport=httpx.MockTransport(handler)
        ) as client:
            response = await client.get("https://agent.test/v1/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transport.calls, 0)

    async def test_401_refreshes_and_retries_once(self) -> None:
        authorizations = []

        async def handler(request):
            authorizations.append(request.headers["Authorization"])
            return httpx.Response(
                401 if len(authorizations) == 1 else 200,
                json={"ok": len(authorizations) > 1},
            )

        async with httpx.AsyncClient(
            auth=self.auth, transport=httpx.MockTransport(handler)
        ) as client:
            response = await client.get("https://agent.test/v1/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            authorizations,
            ["Bearer stale-access", "Bearer fresh-access"],
        )
        self.assertEqual(self.transport.calls, 1)
        self.assertEqual(
            (await self.store.get("grant-1")).refresh_token,
            "fresh-refresh",
        )

    async def test_concurrent_401s_rotate_refresh_token_once(self) -> None:
        stale_requests = 0
        both_stale = asyncio.Event()

        async def handler(request):
            nonlocal stale_requests
            if request.headers["Authorization"] == "Bearer stale-access":
                stale_requests += 1
                if stale_requests == 2:
                    both_stale.set()
                await both_stale.wait()
                return httpx.Response(401)
            return httpx.Response(200)

        async with httpx.AsyncClient(
            auth=self.auth, transport=httpx.MockTransport(handler)
        ) as client:
            responses = await asyncio.gather(
                client.get("https://agent.test/v1/sessions/one"),
                client.get("https://agent.test/v1/sessions/two"),
            )

        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(self.transport.calls, 1)


if __name__ == "__main__":
    unittest.main()
