# MISSION.md — Vocis: A Speech-Forward AI Agent Workflow & Interface

Building a **voice- and chat-native interface** for real-time, speech-driven
work across AI agents, tools, environments, and identities — through a
platform-neutral Voice Gateway.

## Primary Goals

1. **Talk to your agent.** A voice-first interface for OmniGent-managed
   coding agents. The primary interface is voice. Text and UI are secondary.

2. **Talk through your agent.** Voice turns not only instruct agents but
   stream their work back in real time.

3. **Platform-neutral Voice Gateway.** A portable component that any Agent
   Platform (OmniGent, Happier, custom) can mount for voice control.

## Architecture (see ARCHITECTURE.md for full detail)

Voice turns flow through LiveKit (audio transport) → Vocis gateway (control
plane) → Platform Connector → Agent Platform session. Audio never flows
through ACP. LiveKit handles STT/TTS; Vocis handles the completed transcripts.

## Key Files to Explore

- `packages/vocis-core/vocis/` — main Python package
  - `gateway.py` — LiveKitVoiceGateway (message mediator)
  - `livekit_protocol.py` — versioned data message protocol
  - `acp_agent.py` — ACP v1 in-process agent
  - `settings_api.py` — host-neutral VoiceGatewayApi facade
- `packages/vocis-core/vocis/connectors/` — ConnectorRegistry + built-in manifests
- `packages/vocis-core/vocis/connections/` — PlatformConnectionStore
- `packages/vocis-core/vocis/credentials/` — OAuth credential lifecycle
- `packages/vocis-core/vocis/execution/` — PlatformConnectionExecutor
- `packages/vocis-core/vocis/lifecycles/` — connector lifecycle strategies
- `packages/vocis-core/vocis/omnigent_backend.py` — OmniGent SDK adapter
- `packages/vocis-core/vocis/__main__.py` — CLI composition root
- `packages/vocis-ui/src/` — React settings UI
- `packages/vocis-omnigent/src/server/router.py` — OmniGent router factory

## Repo Context

- `ARCHITECTURE.md` — full architecture reference
- `CONTEXT.md` — canonical domain language
- `docs/omnigent.md` — OmniGent platform and vocis integration
- `.claude/skills/` — task-specific progressive disclosure

## Package Layout

```
packages/
  vocis-core/     @vocis/core      — platform-agnostic Voice Gateway
  vocis-ui/       @vocis/ui        — reusable settings UI components
  vocis-omnigent/ @vocis/omnigent  — OmniGent adapter
```
