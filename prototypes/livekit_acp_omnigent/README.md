# LiveKit + ACP + OmniGent prototype

This prototype proves the narrow path that matters:

```text
web/native microphone
  -> LiveKit audio track
  -> LiveKit Agents STT (final transcript only)
  -> voice gateway
  -> official ACP client over stdio
  -> OmniGent ACP bridge
  -> omnigent_client HTTP/SSE
  -> existing OmniGent conv_* session
  -> ACP updates
  -> LiveKit data events + existing TTS audio track
```

LiveKit carries audio and ephemeral realtime events. ACP carries coding-agent
control. OmniGent remains the durable session owner.

## What is implemented

- Versioned LiveKit data envelopes (`v: 1`) and topic `voice.events.v1`.
- Server-side final STT dispatch; partial transcripts never trigger coding work.
- An Agent Session interface consumed by the Voice Gateway.
- ACP v1 agent and client wrappers using the official Python SDK.
- An OmniGent Platform Connector using the supported `omnigent_client` session interface.
- Exact transcript preservation.
- Per-session cancellation.
- Permission requests that remain pending until an explicitly correlated client response.
- Subscribe-before-post handling for OmniGent's no-replay SSE stream.
- Platform Connection execution with renewable Credential Grant injection.
- A host-neutral settings and Voice Session service contract.

## Why ACP v1

ACP v2 existed as `2.0.0-alpha.2` during this prototype, but the upstream schema
still marks protocol version 2 as unstable and identifies version 1 as latest
stable. The prototype therefore targets v1 and keeps protocol-specific code in
the two `acp_sdk_*` adapters.

## Run the tests

The contract tests need only the standard library:

```bash
cd /home/hyggan/voice-agent/prototypes/livekit_acp_omnigent
python3 -m unittest discover -s tests -v
python3 -m compileall -q voice_bridge
```

The slice 8 full-validation test exercises the complete configured path against
an in-process Agent Platform boundary: device authorization, non-secret
Platform Connection persistence, Voice Session startup by public IDs,
authenticated Agent Session attachment, forced 401 refresh and retry, refresh
rotation, revocation, and fail-closed reuse.

```bash
uv run python -m unittest tests.test_slice8_full_validation -v
```

## Run the live voice E2E

The opt-in live system test starts an isolated LiveKit server and real Voice
Gateway worker, launches the ACP bridge through a pre-authorized Platform
Connection, publishes a deterministic WAV as microphone audio, captures the
spoken response, and independently transcribes it. Every explicit run creates
an immutable `.e2e-artifacts/<timestamp>-<run-id>/` proof bundle with:

- `private/`: complete service logs, the event journal, returned WAV, and
  sensitive diagnostics.
- `share/`: a self-contained redacted dashboard, WebM proof replay, untouched
  input WAV, optional returned WAV, evidence JSON, sanitized excerpts, and
  `SHA256SUMS`.

The command atomically updates `.e2e-artifacts/latest` and publishes only the
redacted share bundle into `.e2e-public/runs/<run-id>/`,
`.e2e-public/latest/`, and the `.e2e-public/index.html` history.

Install the opt-in pinned recorder dependencies and the Playwright-managed
Chromium build once. Ordinary runtime requirements are unchanged:

```bash
./scripts/setup-e2e-recording.sh
```

OmniGent must already be running, the target Agent Session must be online, and
the Platform Connection's Credential Grant must already be authorized in the
OS keyring:

```bash
cd /home/hyggan/voice-agent
VOICE_E2E_LIVE=1 \
OMNIGENT_CONNECTION_ID=remote \
OMNIGENT_SESSION_ID=conv_example \
VOICE_CONNECTION_STORE="$HOME/.config/voice-gateway/connections.json" \
venv/bin/python -m unittest discover \
  -s spike -p 'test_live_e2e.py' -v
```

Optional controls include `VOICE_E2E_INPUT_WAV`,
`VOICE_E2E_EXPECTED_PHRASE`, `VOICE_E2E_LISTEN_SECONDS`,
`VOICE_E2E_STARTUP_TIMEOUT_SECONDS`, `VOICE_E2E_ARTIFACT_ROOT`,
`VOICE_E2E_PUBLIC_ROOT`, and `VOICE_E2E_ARTIFACT_DIR`.
Without `VOICE_E2E_LIVE=1`, the test skips so the ordinary suite never starts
services or loads speech models. Missing recording dependencies fail the
`evidenceBundle` outcome with the exact setup command; a passing `liveE2E`
outcome never hides an evidence failure.

## Tailnet-private proof dashboard

Install the scoped loopback server and persistent systemd user service, then
mount it through Tailscale Serve:

```bash
./scripts/setup-e2e-dashboard.sh
```

The service binds only `127.0.0.1:8791`, is rooted at `.e2e-public/`, and has a
`/healthz` endpoint. The installer uses Tailscale Serve at `/voice-e2e`; it
never enables Funnel. It derives the device MagicDNS name from
`tailscale status --json` and reports URLs only after `tailscale serve status`
contains `tailnet only`.

## Live smoke result

Verified locally on 2026-07-22 against LiveKit on `ws://127.0.0.1:7880`,
OmniGent 0.3.0 on `http://127.0.0.1:6767`, the official ACP Python SDK,
and an OmniGent Codex session using `gpt-5.4`:

```text
LiveKit voice.turn.final
  -> voice.turn.accepted
  -> ACP prompt over stdio
  -> OmniGent HTTP/SSE
  -> harness.text.delta: LIVE KIT _AC P _OK
  -> harness.completed: LIVEKIT_ACP_OK
```

The smoke used two real LiveKit participants in a disposable room and asserted
the reconstructed response exactly equalled `LIVEKIT_ACP_OK`. It exercised a
typed final-turn event rather than microphone/STT/TTS; those media components
already belong to the existing worker and remain the next production-wiring
test. The `harness.*` names shown above are legacy compatibility names in the
v1 wire protocol; they do not describe the platform integration boundary.

A separate media-edge smoke also passed on 2026-07-22 using the existing
worker in deterministic probe mode:

```text
reference WAV -> LiveKit microphone track -> local Whisper STT
  -> streaming probe response -> local Kokoro TTS -> LiveKit audio track
  -> captured 48 kHz WAV -> independent Whisper verification
```

The capture contained 7.24 seconds of active audio (`RMS 0.02585`, peak
`0.49118`). Independent transcription recovered the complete expected probe
response. This proves the RTC/STT/TTS media edges, but not yet one continuous
microphone-to-ACP run: the media smoke used the deterministic probe brain while
the ACP smoke injected an authoritative final transcript.

The combined continuous path then passed on 2026-07-22:

```text
spoken WAV -> LiveKit microphone -> Whisper final transcript
  -> ACP stdio -> OmniGent Codex gpt-5.4 -> streamed ACP text
  -> Kokoro -> LiveKit audio -> captured WAV -> independent Whisper
```

Whisper heard the synthetic instruction as “Reply with exactly, voice is CP
complete.” The independently transcribed response was “Voice is CP complete.”
This confirms the same final transcript passed through the entire chain. The
captured response had 1.22 seconds of active speech and peak amplitude 0.47794.

Two operator issues were exposed:

- OmniGent 0.3.0 selected `opus` by default for a Codex Agent Runtime, which is not
  accepted by the configured ChatGPT-backed Codex account. Supplying
  `--model gpt-5.4` succeeded.
- Running the bridge directly inside OmniGent's existing isolated tool
  environment fails if `agent-client-protocol` is absent. Install this project
  as documented below so `omnigent_client` and `acp` share one runtime; do not
  invoke the module with OmniGent's private tool interpreter.

## Run the OmniGent ACP bridge

The bridge intentionally attaches to an existing OmniGent conversation. Start
OmniGent and identify a `conv_*` session, then install/run the prototype in a
Python 3.12 environment:

```bash
uv tool install /home/hyggan/voice-agent/prototypes/livekit_acp_omnigent
omnigent-acp-voice \
  --server http://127.0.0.1:6767 \
  --session conv_example
```

It speaks ACP JSON-RPC over stdin/stdout, so it is normally spawned by the
voice runtime rather than run interactively.

## Use it from the existing LiveKit worker

The current `spike/agent.py` now has an explicit ACP mode. It retains ownership
of microphone audio, final-only Whisper STT, endpointing, and Kokoro TTS while
`spike/acp_voice_llm.py` streams ACP output into LiveKit Agents' normal TTS
pipeline. `spike/acp_harness.py` owns one persistent ACP subprocess per room
job and closes it through the LiveKit job shutdown callback. The
`acp_harness.py` filename and `VOICE_HARNESS` environment variable below are
legacy implementation identifiers retained for compatibility.

Install the two runtimes, start OmniGent, and attach the worker to an existing
online `conv_*` session:

```bash
uv tool install --force /home/hyggan/voice-agent/prototypes/livekit_acp_omnigent
uv pip install --python /home/hyggan/voice-agent/venv/bin/python \
  agent-client-protocol==0.11.0

VOICE_HARNESS=acp \
OMNIGENT_SESSION_ID=conv_example \
OMNIGENT_URL=http://127.0.0.1:6767 \
VOICE_PROJECT_ROOT=/home/hyggan/voice-agent \
LIVEKIT_URL=ws://127.0.0.1:7880 \
LIVEKIT_API_KEY=devkey \
LIVEKIT_API_SECRET=... \
/home/hyggan/voice-agent/venv/bin/python spike/agent.py dev
```

The OmniGent runner for that conversation must remain online. Coding-tool
permission requests currently fail closed; presenting them in the Happier UI
is deliberately left as the next slice rather than granting them implicitly.

## Web/native interface

The existing `happy-src` LiveKit clients can keep publishing microphone audio
and subscribing to the agent audio track. Their `RoomEvent.DataReceived`
handler should additionally accept the versioned messages:

```text
voice.turn.accepted
harness.text.delta
harness.permission.requested
harness.completed
harness.failed
harness.cancelled
```

The client sends only controls over LiveKit data:

```text
voice.turn.cancel
harness.permission.respond
```

The `harness.*` event types are legacy v1 compatibility names. New conceptual
documentation should describe these as Agent Session result and permission
events; renaming the wire values requires a versioned protocol migration.

It does not normally send final transcripts: LiveKit Agents produces the
authoritative server-side final transcript. `voice.turn.final` remains useful
for typed input and test clients.

Durable transcript/result history should continue through the Agent Platform's
application service. LiveKit data is live delivery, not replay storage.

## How it fits OmniGent 0.3.0

The installed OmniGent client exposes exactly the operations needed:

| Prototype operation | OmniGent interface |
|---|---|
| Validate target | `client.sessions.get(conv_id)` |
| Send final transcript | `client.sessions.post_event(..., type="message")` |
| Stream response | `client.sessions.stream(conv_id)` |
| Cancel | `client.sessions.interrupt(conv_id)` |
| Answer permission | `client.sessions.resolve_elicitation(...)` |

The bridge never reads `~/.omnigent/chat.db` and never imports OmniGent server
internals.

## Connector Manifest and Platform Connection

A **Connector Manifest** is trusted, static metadata shipped with a Platform
Connector. It declares the connector identity, ACP version, Capability Set,
authentication methods, and configuration schema. It contains no server
credentials or user tokens. The built-in OmniGent manifest can be inspected
with:

```bash
uv run python -m voice_bridge --list-connectors
```

A **Platform Connection** is one configured relationship to a specific
Agent Platform instance: for example, the OmniGent connector plus
`http://omnigent:6767` and a reference to a separate Credential Grant. Platform
Connection persistence is implemented as validated, atomic, non-secret JSON.
Configured connections can be inspected with:

```bash
uv run python -m voice_bridge --list-connections
```

The legacy ACP-agent CLI still accepts `--server` and an existing `--session`
directly. Application hosts can instead use `PlatformConnectionExecutor` and
`VoiceGatewayApi` to start a Voice Session from Platform Connection, Agent
Session, and Voice Profile IDs. The built-in OmniGent lifecycle injects
renewable HTTP authentication and closes the SDK backend with the execution
context.

The manifest registry currently proves discovery and validation for one
built-in Agent Platform connector and one generic ACP connector. The generic
connector reuses the existing official ACP subprocess lifecycle and requires an
existing Agent Session; it does not claim authentication or session discovery.

Credential Grant device authorization, refresh-token rotation, revocation,
HTTP transport, OS-keyring storage, and authenticated OmniGent execution are
implemented as reusable components. Authorize or revoke a configured
connection with:

```bash
uv run python -m voice_bridge --authorize-connection CONNECTION_ID
uv run python -m voice_bridge --revoke-connection CONNECTION_ID
```

For a disposable Credential Grant, the opt-in live lifecycle smoke performs
device approval, forces token refresh, recreates the resolver and executor,
revokes the grant, and verifies a fresh executor fails closed:

```bash
VOICE_CREDENTIAL_LIFECYCLE_LIVE=1 \
VOICE_CREDENTIAL_LIFECYCLE_ALLOW_REVOKE=1 \
VOICE_CONNECTION_STORE=/path/to/connections.json \
OMNIGENT_CONNECTION_ID=remote \
OMNIGENT_SESSION_ID=conv-id \
uv run python -m unittest tests.test_live_credential_lifecycle -v
```

The smoke intentionally revokes the selected grant. Use a disposable Platform
Connection and expect to authorize it again before later live runs.

The reusable visual settings UI remains a follow-up slice.

## Critical findings from the three voice implementations

### `voice-agent`

Keep:

- LiveKit media transport and local Whisper/Kokoro pipeline.
- Final-transcript-only irreversible dispatch.
- Direct versus mediated brain decision.
- Raw transcript preservation and per-session FIFO work.

Improve:

- The current data protocol is unversioned and split across ad-hoc event types.
- Deleting a room when any participant disconnects is unsafe for multi-device or observer rooms.
- A fixed shared room named `voice` makes session isolation and reconnect semantics harder.
- Agent Platform calls are embedded in the voice front-end instead of satisfying
  a small Agent Session interface.

### `happy-src`

Keep:

- Working LiveKit web/native audio clients.
- Explicit autoplay recovery on web.
- Voice activity and conversation presentation.

Improve:

- URLs and room name are hardcoded in implementation files.
- Data messages lack a versioned envelope and stable topic contract.
- Live activity is persisted directly on the client while delivery and durable application history are mixed.
- Browser/native implementations duplicate substantial connection logic.

### current Happier

Keep:

- Deep Speech Provider coverage and capability-driven model selection.
- Dedicated hidden voice conversation, privacy settings, resumability, typed actions, and barge-in.
- The `VoiceAdapterController` and `VoiceAgentClient` ideas.

Improve for this architecture:

- The orchestration is highly coupled to Happier storage, session bindings, and UI state.
- Local voice and realtime ElevenLabs are separate product paths; a LiveKit adapter should join the voice adapter registry rather than add a third top-level orchestration path.
- The reusable seam should be the Platform Connector's Agent Session interface
  and versioned event protocol, not Happier's internal settings object.

## Deliberate challenge to “ACP everywhere”

ACP is the right baseline at the Agent Protocol seam, but not the entire system:

- Do not carry audio through ACP; use LiveKit.
- Do not use ACP as durable storage; use OmniGent/Happier.
- Do not force OmniGent agent creation into baseline `session/new`. Agent
  Runtime launch configuration, host, sandbox, policy, and agent-tree selection
  do not fit that method.
- Do not hide richer OmniGent features behind undocumented required ACP
  extensions. Add optional extensions only after the baseline path works.

For production, keep an optional native OmniGent capability channel for agent
trees, artifacts, host placement, and cost/policy details. Losing those features
would outweigh the elegance of a pure-ACP-only integration.
