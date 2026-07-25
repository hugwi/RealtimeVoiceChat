# Vocis — Architecture

Platform-neutral voice-to-agent integration. Three packages, layered DAG.

## Packages

| Package | Lang | Role |
|---------|------|------|
| `@vocis/core` | Python | Connector registry, credential resolver, connection executor, LiveKit gateway, ACP bridge |
| `@vocis/ui` | TS+React | Settings UI components + single-spa micro-frontend |
| `@vocis/omnigent` | Python+TS | OmniGent adapter: FastAPI router factory + UI wrappers |

Core responsibilities: LiveKit handles audio (STT/TTS). Vocis handles the
control plane — what to do with completed transcripts. Platform Connectors hide
platform differences. Credentials live in OS keyring, never in config files.

Domain language is in `CONTEXT.md` — read that before naming anything new.

## Layers (top-down dependency DAG)

```
COMPOSITION ROOT
  __main__.py (CLI) │ http_adapter.py (FastAPI)
──
ORCHESTRATION
  VoiceGatewayApi │ PlatformConnectionExecutor │ BuiltinLifecycleRegistry
──
INFRASTRUCTURE
  ConnectorRegistry │ PlatformConnectionStore │ OmnigentCredentialResolver
──
AGENT
  OmnigentAcpAgent │ OfficialSdkOmnigentAgent │ OfficialSdkAcpHarnessClient
──
TRANSPORT
  LiveKitVoiceGateway │ livekit_adapter.py
──
PROTOCOL
  livekit_protocol.py — FinalTurn │ CancelTurn │ PermissionResponse (v=1)
──
SDK ADAPTER
  omnigent_backend.py — OmnigentSdkBackend, BackendEvent
```

Audio never flows through ACP. LiveKit is the sole audio transport. ACP carries
control messages and text over LiveKit data channels (`voice.events.v1`).

## Layer details

### Protocol — `vocis/livekit_protocol.py`

Three immutable, versioned message types (v=1 envelope):
- `FinalTurn(voice_session_id, turn_id, text)`
- `CancelTurn(voice_session_id, turn_id)`
- `PermissionResponse(voice_session_id, turn_id, request_id, decision)`

### Transport — `vocis/gateway.py` + `vocis/livekit_adapter.py`

`LiveKitVoiceGateway` mediates between LiveKit data messages and the harness
backend. `handle_data()` parses → dispatches → publishes versioned events.
Tracks active turns (`voice_session_id → turn_id`). Permission flow blocks on
`asyncio.Future` until the LiveKit client responds.

The adapter (`livekit_adapter.py`) structurally binds the gateway to a LiveKit
room without importing LiveKit SDK types — duck-typing only.

### Agent — 4 classes for 3 execution contexts

| Class | Context |
|-------|---------|
| `OmnigentAcpAgent` | In-process (tests, tracer, direct) |
| `OfficialSdkOmnigentAgent` | ACP JSON-RPC stdio subprocess |
| `OfficialSdkAttachedSessionAgent` | Connection-based (pre-authenticated session) |
| `OfficialSdkAcpHarnessClient` | Generic ACP subprocess as harness backend |

### SDK Adapter — `vocis/omnigent_backend.py`

Adapter over OmniGent SDK. SSE → `BackendEvent` translation:

| SDK event | BackendEvent.kind |
|-----------|-------------------|
| `response.output_text.delta` | `text_delta` |
| `response.elicitation_request` | `permission` |
| `session.status=idle` | `completed` |
| `session.status=error` | `failed` |
| `turn.cancelled` / `response.cancelled` | `cancelled` |

Uses `asyncio.Queue` (background pump reads SSE, foreground yields events).

### Infrastructure

- **ConnectorRegistry** — discovers and validates `*.connector.json` manifests.
  Built-in: `omnigent`, `generic-acp`.
- **PlatformConnectionStore** — atomic JSON persistence (`mkstemp` + `os.replace`
  + `fsync`). Rejects config keys matching `apikey|authorization|bearertoken|credential|credentials|password|secret|token`.
  Validates against connector manifest's JSON Schema on read and write.
- **OmnigentCredentialResolver** — OAuth device flow lifecycle:
  `begin → poll → resolve → refresh(on 401) → revoke`. Refresh token rotation
  (RFC 9700). Per-grant `asyncio.Lock`. Secrets in OS keyring via injectable
  `SecretStore` protocol.

### Orchestration

**PlatformConnectionExecutor** — async context manager, 8-step pipeline:
1. `store.get(connection_id)` → Connection
2. `registry.require(connector_id)` → Manifest
3. `lifecycles.require(connector_id)` → Lifecycle
4. `credentials.resolve(grant_id)` → Credential (if grant exists)
5. `lifecycle.connect(connection, credential)` → `async with` → ConnectedPlatform
6. Select session: explicit ID > config `sessionId` > discovery
7. `platform.attach_session(session_id)` → Agent Session
8. Yield `ConnectionExecution`

**VoiceGatewayApi** — host-neutral facade. `list_connectors()`,
`list_connections()`, `start_voice_session()` (async context manager).

### Lifecycles

Two built-in strategies selected by `connector_id`:
- `OmnigentConnectorLifecycle`: `OmnigentSdkBackend` + `RenewableBearerAuth`
- `GenericAcpConnectorLifecycle`: spawns ACP subprocess via `spawn_generic_acp_connector()`

## @vocis/ui

Headless component library, three entry points:

| Export | Entry | For |
|--------|-------|-----|
| `@vocis/ui` | `dist/core/index.js` | Types + API client |
| `@vocis/ui/react` | `dist/react/index.js` | Direct React import |
| `@vocis/ui/single-spa` | `dist/single-spa/voice-settings.js` | Micro-frontend (react externalized) |

Four components: `ConnectorList`, `ConnectionList`, `ConnectionForm`,
`VoiceSession`. All take `apiBaseUrl` + `authToken?` + callbacks. The
single-spa `SettingsPage` composes them into a tabbed UI.

## @vocis/omnigent

Thin adapter. `create_voice_gateway_router(api) → APIRouter` — factory takes an
already-composed `VoiceGatewayApi`, injects it into pre-configured endpoints
(prefix `/voice-gateway`): `GET /voice-gateway/connectors`, `GET /voice-gateway/connections`,
`POST /voice-gateway/connections` (TODO), `POST /voice-gateway/sessions`. Host composes
the API; router only handles HTTP.

## Module import graph (DAG)

```
vocis/__init__.py  — 6 public exports
  ConnectorRegistry ← connectors/
  PlatformConnectionStore ← connections/
  OmnigentCredentialResolver ← credentials/
  PlatformConnectionExecutor ← execution/
  BuiltinLifecycleRegistry ← lifecycles/
  VoiceGatewayApi ← settings_api.py

__main__.py (composition root) → imports everything above + agent + backend
gateway.py → livekit_protocol.py + omnigent_backend.py
livekit_adapter.py → gateway.py (no SDK import)
settings_api.py → connections/ + connectors/ + execution/

acp_agent.py → omnigent_backend.py
acp_sdk_agent.py → acp_agent.py
acp_sdk_client.py → omnigent_backend.py

connectors/registry.py — standalone
connectors/generic_acp.py → acp_sdk_client.py
connections/store.py → connectors/
credentials/ — standalone (httpx, keyring)

execution/ → connections/ + connectors/
lifecycles/ → acp_agent.py + generic_acp.py + credentials/ + omnigent_backend.py
```

Lower layers never import from higher layers. CLI is the single composition root.

## OmniGent integration

Vocis integrates with [OmniGent](https://github.com/omnigent-ai/omnigent) (the
open-source meta-harness over Claude Code, Codex, Cursor, OpenCode, Hermes, Pi)
through three layers: (1) SDK adapter translating SSE events to `BackendEvent`,
(2) OAuth device-flow credential grants with refresh rotation, (3) Platform
Connection lifecycle orchestrating resolve → connect → select → attach.
Full detail in `docs/omnigent.md`.

## Design patterns

| Pattern | Where |
|---------|-------|
| Protocol (structural typing) | Every dependency boundary |
| Registry / Service Locator | `ConnectorRegistry`, `BuiltinLifecycleRegistry` |
| Adapter / Wrapper | `OmnigentSdkBackend`, ACP SDK wrappers, `livekit_adapter.py` |
| Facade | `VoiceGatewayApi`, `PlatformConnectionExecutor` |
| Repository | `PlatformConnectionStore` (atomic JSON CRUD) |
| Strategy | Credential resolver transport/store, lifecycle by connector_id |
| Mediator | `LiveKitVoiceGateway` |
| Producer-Consumer | SSE streaming (asyncio.Queue), ACP subprocess harness |
| Command Message | `livekit_protocol.py` versioned envelopes |
| Router Factory | `create_voice_gateway_router(api)` |
| State Machine | OAuth device flow |
| Async Context Manager | Executor, lifecycle connect, VoiceSession |

## Key flows

### Voice turn

```
Phone → [audio] → LiveKit → [STT] → voice.turn.final → gateway.dispatch()
  → harness.prompt() → OmniGent/ACP → stream BackendEvent
  → harness.text.delta → LiveKit → [TTS] → [audio] → Phone
```

### Connection execution

```
store.get → registry.require → lifecycles.require
  → credentials.resolve (if grant) → lifecycle.connect
  → select session → attach → yield ConnectionExecution
```

### OAuth device flow

```
POST /oauth/device/authorize → show URL+code to user
  → poll /oauth/token (pending) → poll (success)
  → store in OS keyring → resolve/refresh/revoke
```

## Deployment

```
Host App (FastAPI)        LiveKit Server        Tailscale (tailnet-only)
  Voice Gateway Router      Voice Worker            /voice-gateway → :8788
  /v1/voice-gateway/*       ACP bridge subprocess   :10000 → LiveKit wss
  Single-SPA /settings      STT/TTS pipeline        :8443 → token service
```

Run modes: standalone ACP agent (`uv tool install .`), configured connection
(`python -m vocis --connection`), LiveKit worker (`VOICE_HARNESS=acp`), HTTP
adapter (`python http_adapter.py`).

## Security invariants

- Secrets in OS keyring only. Connection JSON rejects `token|secret|password|apikey|credential` keys.
- Refresh token rotation (RFC 9700). Per-grant `asyncio.Lock`. Stale replay → revocation.
- Revocation: best-effort HTTP + always deletes local secret (fail-closed).
- Manifest validation rejects unknown fields. Tailscale routes are tailnet-only.

## Migration notes (spike → packages)

ponytail: the old spike dir still has working systemd units pointing at it.
`voice-agent-handoff.md` covers the live service state. Don't move units until
Slice 11 (Compose deploy).

| Old (`spike/`) | New | Change |
|----------------|-----|--------|
| `agent.py` | `livekit_adapter.py` | Control plane extracted; SDK stays in runtime |
| `happy_bridge.py` | `acp_sdk_client.py` | CLI → generic ACP JSON-RPC stdio |
| `happy_llm.py` | `gateway.py` + `acp_agent.py` | Blocking → async streaming |
| `voice_state.py`, `data_events.py` | `livekit_protocol.py` | Ad-hoc → v=1 typed protocol |
