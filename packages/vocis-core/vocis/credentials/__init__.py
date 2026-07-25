"""Renewable Credential Grants for OmniGent Platform Connections.

The resolver owns OAuth device-flow protocol behavior. Secret persistence is
injected because this prototype does not yet have an OS credential-store
integration; callers must not substitute the Platform Connection JSON store.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Mapping, Protocol

import httpx


_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
_CLIENT_SECRET_HEADER = "X-Omnigent-Client-Secret"


class CredentialGrantError(RuntimeError):
    """A Credential Grant operation failed."""


class CredentialGrantPending(CredentialGrantError):
    """The user has not approved the device authorization yet."""


class CredentialGrantDenied(CredentialGrantError):
    """The device authorization was denied or revoked."""


class CredentialGrantExpired(CredentialGrantError):
    """The authorization or renewable grant expired."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: Mapping[str, Any]


class HttpTransport(Protocol):
    async def post_json(
        self, url: str, body: Mapping[str, str], headers: Mapping[str, str]
    ) -> HttpResponse: ...

    async def post_form(
        self, url: str, body: Mapping[str, str], headers: Mapping[str, str]
    ) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class StoredCredential:
    access_token: str
    refresh_token: str
    expires_at: float


class SecretStore(Protocol):
    async def get(self, grant_id: str) -> StoredCredential | None: ...

    async def put(self, grant_id: str, credential: StoredCredential) -> None: ...

    async def delete(self, grant_id: str) -> None: ...


class InMemorySecretStore:
    """Non-persistent SecretStore for tests and ephemeral development."""

    def __init__(self) -> None:
        self._credentials: dict[str, StoredCredential] = {}

    async def get(self, grant_id: str) -> StoredCredential | None:
        return self._credentials.get(grant_id)

    async def put(self, grant_id: str, credential: StoredCredential) -> None:
        self._credentials[grant_id] = credential

    async def delete(self, grant_id: str) -> None:
        self._credentials.pop(grant_id, None)


class KeyringSecretStore:
    """Persist rotating device credentials in the operating-system keyring."""

    def __init__(self, service_name: str = "voice-gateway", *, backend: Any = None) -> None:
        if backend is None:
            import keyring

            backend = keyring
        self._service_name = service_name
        self._backend = backend

    async def get(self, grant_id: str) -> StoredCredential | None:
        raw = await asyncio.to_thread(
            self._backend.get_password, self._service_name, grant_id
        )
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            return StoredCredential(
                access_token=_required_string(value, "access_token"),
                refresh_token=_required_string(value, "refresh_token"),
                expires_at=float(value["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CredentialGrantError(
                f"stored Credential Grant {grant_id!r} is invalid"
            ) from exc

    async def put(self, grant_id: str, credential: StoredCredential) -> None:
        value = json.dumps(
            {
                "access_token": credential.access_token,
                "refresh_token": credential.refresh_token,
                "expires_at": credential.expires_at,
            },
            separators=(",", ":"),
        )
        await asyncio.to_thread(
            self._backend.set_password, self._service_name, grant_id, value
        )

    async def delete(self, grant_id: str) -> None:
        if await self.get(grant_id) is not None:
            await asyncio.to_thread(
                self._backend.delete_password, self._service_name, grant_id
            )


class HttpxTransport:
    """Use OmniGent's existing async HTTP dependency for device authorization."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def post_json(
        self, url: str, body: Mapping[str, str], headers: Mapping[str, str]
    ) -> HttpResponse:
        return _http_response(
            await self._client.post(url, json=body, headers=headers)
        )

    async def post_form(
        self, url: str, body: Mapping[str, str], headers: Mapping[str, str]
    ) -> HttpResponse:
        return _http_response(
            await self._client.post(url, data=body, headers=headers)
        )


@dataclass(frozen=True, slots=True)
class DeviceAuthorization:
    verification_url: str
    user_code: str
    expires_at: float
    poll_interval: int


@dataclass(frozen=True, slots=True)
class _PendingAuthorization:
    server_url: str
    device_code: str
    expires_at: float
    poll_interval: int


class OmnigentCredentialResolver:
    """Acquire, resolve, rotate, and revoke OmniGent device grants."""

    def __init__(
        self,
        transport: HttpTransport,
        secrets: SecretStore,
        *,
        client_secret: str | None = None,
        clock: Callable[[], float] = time.time,
        refresh_skew_seconds: int = 60,
    ) -> None:
        self._transport = transport
        self._secrets = secrets
        self._client_secret = client_secret
        self._clock = clock
        self._refresh_skew = refresh_skew_seconds
        self._pending: dict[str, _PendingAuthorization] = {}
        self._servers: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def begin(
        self, grant_id: str, *, server_url: str, client_id: str
    ) -> DeviceAuthorization:
        server_url = _server_url(server_url)
        response = await self._transport.post_json(
            f"{server_url}/oauth/device/authorize",
            {"client_id": client_id},
            self._headers(),
        )
        if response.status in (404, 405):
            raise CredentialGrantError(
                f"device authorization is not enabled on {server_url}"
            )
        if response.status != 200:
            raise CredentialGrantError(
                f"device authorization failed: {_error(response)}"
            )
        try:
            device_code = _required_string(response.body, "device_code")
            verification_url = _required_string(
                response.body, "verification_uri_complete"
            )
            user_code = str(response.body.get("user_code", ""))
            expires_in = max(int(response.body.get("expires_in", 600)), 1)
            poll_interval = max(int(response.body.get("interval", 5)), 1)
        except (TypeError, ValueError) as exc:
            raise CredentialGrantError(
                f"malformed device authorization response: {exc}"
            ) from exc
        expires_at = self._clock() + expires_in
        self._pending[grant_id] = _PendingAuthorization(
            server_url, device_code, expires_at, poll_interval
        )
        self._servers[grant_id] = server_url
        return DeviceAuthorization(
            verification_url, user_code, expires_at, poll_interval
        )

    async def poll(self, grant_id: str) -> bool:
        pending = self._pending.get(grant_id)
        if pending is None:
            raise CredentialGrantError(
                f"no pending device authorization for {grant_id!r}"
            )
        if self._clock() >= pending.expires_at:
            self._pending.pop(grant_id, None)
            raise CredentialGrantExpired("the device authorization expired")
        response = await self._transport.post_form(
            f"{pending.server_url}/oauth/token",
            {
                "grant_type": _DEVICE_GRANT_TYPE,
                "device_code": pending.device_code,
            },
            self._headers(),
        )
        error = _error(response)
        if response.status != 200:
            if error in ("authorization_pending", "slow_down"):
                return False
            self._pending.pop(grant_id, None)
            if error == "access_denied":
                raise CredentialGrantDenied("the device authorization was denied")
            if error == "expired_token":
                raise CredentialGrantExpired("the device authorization expired")
            raise CredentialGrantError(f"token request failed: {error}")
        credential = self._credential(response)
        await self._secrets.put(grant_id, credential)
        self._pending.pop(grant_id, None)
        return True

    async def resolve(self, grant_id: str, *, server_url: str | None = None) -> str:
        return await self._resolve(grant_id, server_url=server_url)

    async def refresh(
        self,
        grant_id: str,
        *,
        server_url: str,
        stale_access_token: str,
    ) -> str:
        """Refresh after an API rejected ``stale_access_token``.

        Passing the rejected token prevents concurrent 401 responses from
        rotating the same single-use refresh token more than once.
        """
        return await self._resolve(
            grant_id,
            server_url=server_url,
            stale_access_token=stale_access_token,
        )

    async def _resolve(
        self,
        grant_id: str,
        *,
        server_url: str | None = None,
        stale_access_token: str | None = None,
    ) -> str:
        async with self._locks.setdefault(grant_id, asyncio.Lock()):
            credential = await self._secrets.get(grant_id)
            if credential is None:
                raise CredentialGrantError(
                    f"Credential Grant {grant_id!r} is not authorized"
                )
            if (
                stale_access_token is not None
                and credential.access_token != stale_access_token
            ):
                return credential.access_token
            if (
                stale_access_token is None
                and self._clock() + self._refresh_skew < credential.expires_at
            ):
                return credential.access_token
            endpoint = _server_url(server_url or self._servers.get(grant_id, ""))
            response = await self._transport.post_form(
                f"{endpoint}/oauth/token",
                {
                    "grant_type": "refresh_token",
                    "refresh_token": credential.refresh_token,
                },
                self._headers(),
            )
            if response.status != 200:
                await self._secrets.delete(grant_id)
                error = _error(response)
                if error == "expired_token":
                    raise CredentialGrantExpired("the Credential Grant expired")
                if error in ("access_denied", "invalid_grant"):
                    raise CredentialGrantDenied(
                        "the Credential Grant was revoked or reused"
                    )
                raise CredentialGrantError(f"refresh failed: {error}")
            try:
                refreshed = self._credential(response)
            except CredentialGrantError:
                # The refresh token was already consumed even if the 200 body
                # is unusable; retaining it would trigger server-side replay
                # detection on the next attempt.
                await self._secrets.delete(grant_id)
                raise
            await self._secrets.put(grant_id, refreshed)
            self._servers[grant_id] = endpoint
            return refreshed.access_token

    async def revoke(self, grant_id: str, *, server_url: str | None = None) -> None:
        credential = await self._secrets.get(grant_id)
        try:
            if credential is not None:
                endpoint = _server_url(server_url or self._servers.get(grant_id, ""))
                await self._transport.post_form(
                    f"{endpoint}/oauth/revoke",
                    {"refresh_token": credential.refresh_token},
                    self._headers(),
                )
        finally:
            self._pending.pop(grant_id, None)
            self._servers.pop(grant_id, None)
            await self._secrets.delete(grant_id)

    def _credential(self, response: HttpResponse) -> StoredCredential:
        try:
            access_token = _required_string(response.body, "access_token")
            refresh_token = _required_string(response.body, "refresh_token")
            expires_in = max(int(response.body.get("expires_in", 3600)), 1)
        except (TypeError, ValueError) as exc:
            raise CredentialGrantError(f"malformed token response: {exc}") from exc
        return StoredCredential(
            access_token, refresh_token, self._clock() + expires_in
        )

    def _headers(self) -> Mapping[str, str]:
        if self._client_secret:
            return {_CLIENT_SECRET_HEADER: self._client_secret}
        return {}


class RenewableBearerAuth(httpx.Auth):
    """Inject a renewable Credential Grant into OmniGent HTTP requests."""

    def __init__(
        self,
        resolver: OmnigentCredentialResolver,
        grant_id: str,
        *,
        server_url: str,
    ) -> None:
        self._resolver = resolver
        self._grant_id = grant_id
        self._server_url = _server_url(server_url)

    async def async_auth_flow(self, request: httpx.Request):
        token = await self._resolver.resolve(
            self._grant_id, server_url=self._server_url
        )
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code != 401:
            return
        token = await self._resolver.refresh(
            self._grant_id,
            server_url=self._server_url,
            stale_access_token=token,
        )
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


def _server_url(value: str) -> str:
    value = value.rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise CredentialGrantError("server_url must be an HTTP(S) URL")
    return value


def _required_string(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _error(response: HttpResponse) -> str:
    value = response.body.get("error")
    return value if isinstance(value, str) and value else f"HTTP {response.status}"


def _http_response(response: Any) -> HttpResponse:
    try:
        body = response.json()
    except (TypeError, ValueError):
        body = {}
    return HttpResponse(
        status=int(response.status_code),
        body=body if isinstance(body, Mapping) else {},
    )


__all__ = [
    "CredentialGrantDenied",
    "CredentialGrantError",
    "CredentialGrantExpired",
    "DeviceAuthorization",
    "HttpResponse",
    "HttpTransport",
    "HttpxTransport",
    "InMemorySecretStore",
    "KeyringSecretStore",
    "OmnigentCredentialResolver",
    "RenewableBearerAuth",
    "SecretStore",
    "StoredCredential",
]
