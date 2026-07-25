# Agent Instructions

## Architecture

`ARCHITECTURE.md` is the source of truth for package structure, layers, module
graph, design patterns, data flows, and security invariants. Keep it accurate
when structure changes. `CONTEXT.md` holds the canonical domain language.
`docs/omnigent.md` explains the OmniGent platform and how Vocis integrates.

## Progressive disclosure

Task-specific instructions live in `.claude/skills/`, loaded on demand:

| Skill | For |
|-------|-----|
| `voice-testing` | End-to-end voice pipeline testing |
| `credential-grants` | OAuth device flow, keyring secrets, token lifecycle |
| `livekit-ops` | LiveKit server, token service, agent worker operations |
| `new-connector` | Adding a new Platform Connector (manifest + lifecycle + tests) |

## Commands

```bash
npm install && cd packages/vocis-core && uv sync   # install
npm test                                            # all tests
cd packages/vocis-core && pytest                     # single package
cd packages/vocis-ui && npm run typecheck            # type check
```

## Conventions

- Reuse existing code, stdlib, native features, installed deps before adding.
- Prefer deletion over addition. No new abstractions unprompted.
- Simplification ceiling → brief `ponytail:` comment naming the tradeoff.
- Map user synonyms to canonical terms silently; don't introduce new names.

## Constraints

- Secrets live in OS keyring only. Connection JSON rejects `token|secret|password|apikey|credential` keys.
- Tailscale Serve only, never Funnel. Routes must report `tailnet only`.
- Lower layers never import from higher layers (DAG — see ARCHITECTURE.md §7).

## Task Tracking

Beads database (`.beads/`) is the canonical task manager.
`bd ready` / `bd list` / `bd show <id>` before starting.
`bd update` / `bd note` / `bd close` as work progresses.
Include bead IDs in handoffs. No parallel todo boards unless explicitly asked.
