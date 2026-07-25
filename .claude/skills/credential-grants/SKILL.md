# Credential Grants

Manage OAuth device flow credentials for OmniGent Platform Connections.

## Overview

Credentials live in the OS keyring, never in Platform Connection JSON.
The connection file stores only a `credential_grant_id` reference.

```
begin() → poll() [pending] → poll() [success]
  → resolve() [cached token] → refresh() [on 401] → revoke()
```

## Authorize a new connection

```bash
python -m vocis --authorize-connection <connection-id>
```

This will:
1. Start OAuth device flow with OmniGent
2. Print a verification URL and user code
3. Poll until approved
4. Store credential in OS keyring

## Check credential status

```bash
python -m vocis --list-connections
# Look for credential_grant_id — if set, a grant exists
```

## Revoke a connection

```bash
python -m vocis --revoke-connection <connection-id>
# Best-effort HTTP revoke + always deletes local secret
```

## Run with a connection (uses cached credential)

```bash
python -m vocis --connection <connection-id> --session <session-id>
# Auto-resolves credential from keyring, refreshes if expired
```

## Security invariants

- Secrets in OS keyring only. Connection JSON rejects `token|secret|password|apikey|credential` keys.
- Refresh token rotation (RFC 9700): every refresh produces a new refresh token
- Stale refresh token replay → grant revocation
- Per-grant `asyncio.Lock` prevents concurrent double-refresh
- Revocation: best-effort HTTP + always deletes local secret (fail-closed)

## Testing

```bash
# Unit tests (mocked HTTP transport)
pytest tests/test_credential_grants.py -v
pytest tests/test_renewable_http_auth.py -v
pytest tests/test_device_auth_cli.py -v

# Full validation (mock HTTP)
pytest tests/test_slice8_full_validation.py -v

# Live smoke test (against real OmniGent)
VOICE_CREDENTIAL_LIFECYCLE_LIVE=1 \
VOICE_CREDENTIAL_LIFECYCLE_ALLOW_REVOKE=1 \
pytest tests/test_live_credential_lifecycle.py -v
```

## Implementation

- `vocis/credentials/__init__.py` — `OmnigentCredentialResolver`, `SecretStore` protocol, `KeyringSecretStore`, `HttpxTransport`, `RenewableBearerAuth`
- `vocis/connections/store.py` — `PlatformConnectionStore` (rejects secrets on disk)
- OAuth flow: `POST /oauth/device/authorize` → `POST /oauth/token` (device_code grant) → `POST /oauth/token` (refresh_token grant) → `POST /oauth/revoke`
