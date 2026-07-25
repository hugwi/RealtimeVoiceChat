# Voice Testing

Test the Vocis voice pipeline. Vocis is a library integrated into an OmniGent
or Happier host — it has no standalone services.

## Architecture

```
Phone mic → LiveKit → STT → Vocis gateway → ACP bridge → Agent Platform session
  → response text → TTS → LiveKit → Phone speaker
```

Vocis owns the gateway + ACP bridge. LiveKit and the agent platform (OmniGent)
are external services Vocis connects to.

## In-process tests (no external services)

```bash
cd packages/vocis-core

# Transcript tracer — turn → agent → streaming text back
pytest tests/test_tracer.py -v

# Cancellation — cancel interrupts only the mapped session
pytest tests/test_cancellation.py -v

# Permissions — elicitation blocks until client responds
pytest tests/test_permissions.py -v

# LiveKit adapter — data messages translated to harness calls
pytest tests/test_livekit_adapter.py -v

# Backend event translation — SSE events → BackendEvent
pytest tests/test_omnigent_backend.py -v
```

## Connection execution tests (mock transports)

```bash
# Full executor pipeline with mock OmniGent
pytest tests/test_connection_execution.py -v
pytest tests/test_builtin_lifecycle.py -v
pytest tests/test_attached_session_agent.py -v

# Generic ACP subprocess connector (real subprocess)
pytest tests/test_generic_acp_connector.py -v
```

## Credential lifecycle tests

```bash
# Unit tests (mocked HTTP)
pytest tests/test_credential_grants.py -v
pytest tests/test_renewable_http_auth.py -v
pytest tests/test_device_auth_cli.py -v

# Full validation (mock HTTP, full pipeline)
pytest tests/test_slice8_full_validation.py -v

# Live smoke test (real OmniGent instance required)
VOICE_CREDENTIAL_LIFECYCLE_LIVE=1 \
VOICE_CREDENTIAL_LIFECYCLE_ALLOW_REVOKE=1 \
pytest tests/test_live_credential_lifecycle.py -v
```

## Settings API tests

```bash
pytest tests/test_slice8_api.py -v
pytest tests/test_platform_connections.py -v
pytest tests/test_connector_registry.py -v
```

## Voice turn pipeline (against a running OmniGent)

```bash
# 1. Authorize a Platform Connection
python -m vocis --authorize-connection conn-1

# 2. Run with a connection (text-only, no audio)
python -m vocis --connection conn-1 --session <omnigent-session-id>
# Type a message, verify text deltas stream back

# 3. List available connectors and connections
python -m vocis --list-connectors
python -m vocis --list-connections
```

## Run all tests

```bash
cd packages/vocis-core
pytest -v
```
