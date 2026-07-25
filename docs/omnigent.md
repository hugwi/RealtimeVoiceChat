# OmniGent — how it works and how Vocis integrates

## What OmniGent is

[OmniGent](https://github.com/omnigent-ai/omnigent) is an open-source
**meta-harness** — a common orchestration layer over multiple coding agent
runtimes. It lets you:

- Run Claude Code, Codex, Cursor, OpenCode, Hermes, Pi, Kiro from one CLI/UI
- Swap or combine agents without rewriting tooling
- Enforce policies (approval gates, spend caps, tool limits)
- Collaborate in real time from terminal, browser, phone, desktop app

**Version:** 0.7.0.dev0 (Apache 2.0). ~1,800 commits, 7.7k stars.
Source repo: `github.com/omnigent-ai/omnigent`.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  OmniGent Server (FastAPI, :6767)                    │
│                                                      │
│  ┌─────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │ Web UI  │  │ REST API │  │ Session Management  │  │
│  │ (React) │  │ (SSE)    │  │ (persist, relay)    │  │
│  └─────────┘  └──────────┘  └────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  Harness Layer (agent runtime wrappers)       │    │
│  │                                              │    │
│  │  Native (tmux/bwrap):   SDK (in-process):    │    │
│  │  ├─ claude-native        ├─ claude-sdk        │    │
│  │  ├─ codex-native         ├─ codex             │    │
│  │  ├─ cursor-native        ├─ cursor            │    │
│  │  ├─ hermes-native        ├─ openai-agents     │    │
│  │  ├─ pi-native            └─ polly/debby       │    │
│  │  └─ kiro-native                              │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  Policies Engine                             │    │
│  │  (stackable: server > agent > session)        │    │
│  │  • approval gates (ask on OS tools)           │    │
│  │  • spend caps (USD budget)                    │    │
│  │  • tool-call limits                           │    │
│  │  • CEL expression rules                       │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  Sandboxing (per-session isolation)            │    │
│  │  • bwrap/seatbelt filesystem + network         │    │
│  │  • L7 egress proxy with credential rewriting   │    │
│  │  • Managed hosts: Modal, Daytona, E2B, etc.   │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

### Key concepts

| Concept | What it is |
|---------|-----------|
| **Harness** | A wrapper that launches and controls one kind of agent runtime (Claude Code, Codex, etc.) |
| **Session** | One persistent agent conversation. Agents run turns, use tools, produce results. |
| **ACP** | Agent Control Protocol — standardized event/control contract. Clients discover, observe, and control sessions through it. |
| **Machine / Host** | A registered computer that can run agent sessions. The server dispatches sessions to machines. |
| **Model Provider** | Credential kind: API key, subscription (Claude Pro/Max), gateway (OpenRouter/Ollama), or Databricks workspace. |
| **Policy** | Governance rule checked on every action. Three tiers: server-wide, per-agent, per-session. |
| **Sub-agent** | An agent that a supervisor agent can delegate work to. Runs in a parallel git worktree. |
| **System prompt** | Composed from: agent YAML `prompt:` + user-authored instructions + framework-owned instructions (appended by `omnigent/runtime/prompt.py`). |

### Protocol

OmniGent's client-server API uses:
- **REST** for CRUD (sessions, machines, credentials)
- **SSE** (Server-Sent Events) for real-time streaming: text deltas, elicitation
  requests (permissions), session status changes
- **ACP v1** for the agent-to-platform protocol — the standardized interface
  that vocis bridges through

## How Vocis integrates with OmniGent

Vocis is a **Voice Gateway** that sits between LiveKit (voice transport) and
OmniGent (agent platform). The integration has three layers:

### Layer 1: SDK Adapter — `vocis/omnigent_backend.py`

Adapts the OmniGent Python SDK (`omnigent_client`) into vocis's internal
`OmnigentBackend` protocol:

```
LiveKitVoiceGateway → OmnigentBackend (protocol) → OmnigentSdkBackend (adapter) → omnigent_client SDK → OmniGent HTTP/SSE
```

The adapter:
- Lazily imports `omnigent_client` (optional dependency)
- Authenticates with `OMNIGENT_AUTH_TOKEN` env var (bearer token)
- Translates SSE events into `BackendEvent` instances:
  - `response.output_text.delta` → `text_delta`
  - `response.elicitation_request` → `permission`
  - `session.status=idle` → `completed`
  - `turn.completed` → `completed`
  - `session.status=error` → `failed`
  - `response.failed`, `response.error`, `turn.failed` → `failed` (with error text)
  - `turn.cancelled`, `response.cancelled`, `session.interrupted` → `cancelled`
  - `response.completed` → suppressed (idle edge is the turn-end authority)
- Uses `asyncio.Queue` for streaming (background pump reads SSE, foreground yields events)

### Layer 2: Credential Grant — `vocis/credentials/`

Manages long-lived OAuth authorization with OmniGent:
- **OAuth device flow** (RFC 8628): browserless authorization
  - `begin()` → OmniGent returns device_code + verification URL + user code
  - User opens URL in browser, enters code, approves
  - `poll()` → waits for authorization (handles `authorization_pending`, `slow_down`)
  - `resolve()` → returns access token
- **Refresh token rotation** (RFC 9700): on 401, refreshes credentials
  - Per-grant `asyncio.Lock` prevents concurrent double-refresh
  - Stale refresh token replay triggers grant revocation
- **Secret storage**: `SecretStore` protocol → OS keyring via `keyring` library
- **httpx integration**: `RenewableBearerAuth` auto-injects tokens, retries on 401

### Layer 3: Platform Connection — `vocis/execution/` + `vocis/lifecycles/`

The full connection lifecycle:
1. Connector manifest (`omnigent.connector.json`) declares capabilities and auth methods
2. Platform Connection stores non-secret config (server URL, session ID)
3. Credential Grant stores secrets in OS keyring
4. `OmnigentConnectorLifecycle` knows how to start/stop an OmniGent backend
5. `PlatformConnectionExecutor` orchestrates: resolve credentials → connect → select session → attach

### ACP Bridge — `vocis/acp_agent.py` + `vocis/acp_sdk_agent.py`

The ACP bridge connects vocis to OmniGent sessions:
- `OmnigentAcpAgent`: in-process ACP v1 agent that wraps an `OmnigentBackend`
- `OfficialSdkOmnigentAgent`: wraps the core agent in the official `acp` Python
  SDK types, for running as a JSON-RPC stdio subprocess
- `OfficialSdkAttachedSessionAgent`: wraps a pre-attached session (used in
  connection-based execution where OmniGent session is already authenticated)

## OmniGent API endpoints vocis uses

| Endpoint | Purpose | Used by |
|----------|---------|---------|
| `POST /oauth/device/authorize` | Start device flow | `credentials/` |
| `POST /oauth/token` | Poll/poll-success/refresh | `credentials/` |
| `POST /oauth/revoke` | Revoke grant | `credentials/` |
| SSE session events | Stream agent output | `omnigent_backend.py` |
| Session API (via SDK) | Attach, send message, cancel | `omnigent_backend.py` |

## Key design decisions

1. **Attach-only**: Vocis attaches to existing OmniGent sessions. Creating new
   sessions requires bundle/harness config that ACP baseline `session/new`
   can't express safely.
2. **Secrets in keyring, not config**: The Platform Connection JSON never
   contains tokens. Credentials are in OS keyring, referenced by grant ID.
3. **ACP v1**: Protocol version 1 is used because v2 is explicitly unstable.
4. **Audio never flows through ACP**: LiveKit is the sole audio transport. ACP
   carries control messages and text only.

## Useful OmniGent commands

```bash
# Start OmniGent server locally
omnigent server --background

# List server status
omnigent server status

# Stop everything
omnigent stop

# Run an agent
omnigent claude          # Claude Code native
omnigent codex           # Codex native
omnigent opencode        # OpenCode native

# Run a custom agent
omnigent run path/to/agent.yaml

# Manage credentials
omnigent setup

# Deploy (Docker)
docker compose up -d    # from deploy/
```

## References

- [OmniGent README](https://github.com/omnigent-ai/omnigent)
- [OmniGent AGENTS.md](https://github.com/omnigent-ai/omnigent/blob/main/AGENTS.md)
- [OmniGent deploy guide](https://github.com/omnigent-ai/omnigent/blob/main/deploy/README.md)
- [OmniGent policies](https://github.com/omnigent-ai/omnigent/blob/main/docs/POLICIES.md)
- [Agent YAML spec](https://github.com/omnigent-ai/omnigent/blob/main/docs/AGENT_YAML_SPEC.md)
- [OmniGent OAuth device flow config](https://github.com/omnigent-ai/omnigent/blob/main/docs/device_oauth.md)
