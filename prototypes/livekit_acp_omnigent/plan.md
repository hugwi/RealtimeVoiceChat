# LiveKit + ACP + OmniGent prototype

| Slice | Checkpoint | Scope | Verification | Depends on |
|---|---|---|---|---|
| slice-1 transcript tracer | Complete: a versioned LiveKit final-turn message reaches an OmniGent session through an in-process ACP client and streams text/status events back | `voice_bridge/{livekit_protocol,gateway,acp_agent,omnigent_backend}.py`, tracer test | `python -m unittest tests.test_tracer -v` | - |
| slice-2 cancellation | Complete: a LiveKit cancel command interrupts only the mapped OmniGent session and reports cancellation | gateway, ACP agent, backend, cancellation test | `python -m unittest tests.test_cancellation -v` | slice-1 |
| slice-3 permissions | Complete: an OmniGent elicitation becomes an ACP permission request and stays pending until the LiveKit client responds | gateway, ACP agent, backend, permission test | `python -m unittest tests.test_permissions -v` | slice-1 |
| slice-4 runnable bridge | Complete at contract level: the ACP bridge runs over JSON-RPC stdio against OmniGent's supported HTTP/SSE SDK | `acp_sdk_agent.py`, `acp_sdk_client.py`, `__main__.py`, README | `python -m unittest discover -s tests -v`; official SDK import check | slices 1-3 |
| slice-5 Connector Manifest | Complete: the existing CLI discovers and validates a built-in OmniGent Platform Connector manifest and can list its ACP version and Capability Set | `voice_bridge/connectors/`, `__main__.py`, connector registry tests | `python -m unittest tests.test_connector_registry -v`; `python -m voice_bridge --list-connectors` | slice-4 |
| slice-6 Platform Connections | Complete: validated non-secret Platform Connections reference a Connector Manifest and separate Credential Grant, persist atomically, and can be listed by the existing CLI | `voice_bridge/connections/`, `__main__.py`, Platform Connection tests, README | `python -m unittest tests.test_platform_connections -v`; `python -m voice_bridge --list-connections` | slice-5 |
| slice-7 Credential Grants | Complete at component level: OmniGent device authorization can acquire, resolve, serialize refresh rotation, and revoke a Credential Grant through the existing HTTP stack and OS keyring without putting secrets in Platform Connection JSON | `voice_bridge/credentials/`, expiry/refresh/concurrency/keyring/HTTP tests | Component tests pass; live browser approval and backend injection move to slice-8 | slice-6 |
| slice-8 connection execution and API | Complete: contract validation covers authorization/renewal/revocation, and an opt-in live E2E drives microphone audio through an isolated LiveKit server, the real worker, a configured Platform Connection, ACP, OmniGent, and returned independently transcribed speech | connector lifecycle, connection selection, credential resolution, API, contract tests, `spike/test_live_e2e.py` | `uv run python -m unittest tests.test_slice8_full_validation -v`; `VOICE_E2E_LIVE=1 ... venv/bin/python -m unittest discover -s spike -p 'test_live_e2e.py' -v` | slice-7 |
| slice-9 reusable settings UI | Pending: an Agent Platform web app can mount reusable connector, connection, session, and Voice Profile components without importing OmniGent-specific behavior | reusable UI package/components, OmniGent host integration, accessibility and browser tests | Configure a connection and start a Voice Session from the OmniGent web app | slice-8 |
| slice-10 second Platform Connector | Complete at contract level: a built-in generic ACP connector honestly loads the existing platform-neutral ACP subprocess lifecycle, uses auth `none`, and requires an executable plus existing Agent Session | generic ACP manifest, zero-copy lifecycle aliases, manifest and Platform Connection contract tests | Both connectors are discovered and packaged; live connection selection moves to slice-8 | slice-6 |
| slice-11 Compose deployment | Deferred: an OmniGent Docker Compose installation can enable the Voice Gateway by adding one service or override file, with documented networking, environment variables, health checks, persistent configuration, LiveKit connectivity, and connector discovery | Voice Gateway container image, Compose service/override, deployment documentation, smoke test | Start OmniGent plus the Voice Gateway from a clean Compose project; verify health, connector discovery, and one microphone-to-Agent Session-to-TTS turn | slices 7-9 |
| slice-12 recorded E2E evidence | Complete: every explicit live run separates live/evidence outcomes, records exact WAV audio into an immutable redacted proof dashboard/WebM bundle, retains private diagnostics separately, and publishes history through a loopback-only tailnet Serve mount | `spike/{test_live_e2e,e2e_evidence,e2e_dashboard_server}.py`, recording requirements/setup, systemd template, evidence tests | `venv/bin/python -m unittest discover -s spike -p 'test_e2e_evidence.py' -v`; `./scripts/setup-e2e-dashboard.sh`; explicit live run | slice-8 |

A typed-turn end-to-end smoke passed on 2026-07-22 using a disposable OmniGent
Codex session and two participants in a real local LiveKit room. A separate
microphone/STT/TTS media-edge smoke also passed with independently transcribed
return audio. The ACP harness is now wired into the existing worker behind
`VOICE_HARNESS=acp`, and the continuous microphone-to-ACP-to-TTS run passed.
Happier permission presentation remains a fail-closed follow-up slice.

## Confirmed public seams

1. LiveKit data messages use the versioned envelopes in `livekit_protocol.py`.
2. The Voice Gateway depends on an Agent Session interface, not OmniGent.
3. The ACP agent depends on an `OmnigentBackend` interface; the production adapter alone imports `omnigent_client`.
4. Tests exercise those interfaces and never inspect OmniGent storage or implementation state.
5. Connector Manifests are trusted operator-installed metadata. They contain no credentials; each authenticated Platform Connection references a separate Credential Grant.

## Deliberate limits

- LiveKit remains the media/realtime transport. ACP never carries audio.
- The tracer accepts final transcripts only; existing LiveKit Agents STT/TTS remains responsible for audio tracks.
- ACP protocol version 1 is used because version 2 is still explicitly unstable as of 2026-07-22.
- The first bridge attaches to an existing OmniGent session. Creating arbitrary OmniGent agents requires bundle/harness configuration that ACP's baseline `session/new` cannot express safely.
