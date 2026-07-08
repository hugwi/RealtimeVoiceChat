# Voice → Claude Bridge v2 — Focus-Aware Sessions — Design

**Date**: 2026-07-08
**Status**: Approved for planning
**Working dir**: `/home/hyggan/voice-agent`
**Branch**: `feat/voice-claude-bridge`
**Builds on**: `2026-07-08-voice-claude-bridge-design.md` (v1 shipped and working)

## Problem

v1 pipes voice → Claude via `happy-agent`, but targets the **newest-active**
session. With multiple active sessions this **sprays** across them per utterance
and can hit the *control* session. v1 mitigates by **pinning** one session id via
`VOICE_SESSION_ID` (systemd override) — a static workaround, not a fix.

The real fix: **the phone knows which session is focused; the box does not.**
Focus is phone-only UI navigation state. v2 gets the focused-session id from the
phone to the bridge so voice routes to the session the user is actually looking
at, and adds a **completion ping** when a *background* session finishes.

## Decision: Route B — structured data channel messages

The Happy app already runs a local-LiveKit voice path
(`RealtimeVoiceSession.tsx`) that `publishData`s into the same room the Python
agent joins. The app's `voiceHooks` already fire on focus, ready, and permission
events. v2 adds **two structured message types** the app publishes and the Python
agent consumes. This keeps the bridge server-side (Route A architecture) while
getting focus knowledge from the phone (Route B goal) with a **tiny app change**
instead of fragile string parsing.

Alternatives considered and rejected:
- **Parse existing text strings** (`"Session became focused: <id>"` from
  `contextFormatters.ts`): zero app change, but brittle — silent breakage if the
  app changes those human-readable strings. Rejected in favor of an explicit
  contract.
- **Poll `happy-agent status`**: no app change and no data-channel dependency,
  but polling latency on pings, extra subprocess overhead, and races when
  sessions complete near-simultaneously. Redundant once Route B is chosen; the
  only genuinely useful poll (session state at voice-start) is a single
  `happy-agent list` call on room connect, already in this design.

## Scope

**In:**
- Focus-aware session targeting (phone → bridge over LiveKit data channel).
- Completion ping for **background** sessions (`onReady` → spoken one-liner).

**Out (deferred):**
- **Voice-approve permissions.** BLOCKED: `happy-agent` has no `allow`/`deny`
  command; the real approval path (`sessionAllow`/`sessionDeny` in
  `sync/ops.ts`) is app-side only. Keep v1 behavior — speak the permission notice,
  user taps approve in the app.
- Conversational streaming + acknowledgment (backlog #6).
- Turn detection / endpointing (backlog #7).

## Architecture

```
[Phone app]                          [Python agent / box]
  onSessionFocus(id)
    → publishData({type:'focused_session', sessionId})  ──→  voice_state.focused_session_id = id

  onReady(id)
    → publishData({type:'session_complete', sessionId}) ──→  speak "Your <summary> session finished"
                                                             (only if background, not focused)
  onPermissionRequested(...)
    → publishData (existing v1 behavior)                ──→  speak permission notice (unchanged)

[User speaks]
  → whisper STT → HappyBridgeLLM
      → resolve_session_id(override=VOICE_SESSION_ID, focused=focused_session_id)
      → happy-agent send / history --wait → summarizer → Kokoro TTS → spoken reply
```

## Components

### New: `spike/voice_state.py`
Shared mutable state between the data-channel handler and `HappyBridgeLLM`:
```python
focused_session_id: str | None   # set by data channel focus events
```
Plain object. All access is on the asyncio event loop — no locks needed.

### New: `spike/data_events.py`
Isolated parser for structured data-channel messages. One place that knows the
wire format, so coupling to the app protocol is testable and contained.
- `parse(raw: bytes) -> Event | None`
  - `{type:'focused_session', sessionId}` → `FocusEvent(session_id)`
  - `{type:'session_complete', sessionId}` → `CompleteEvent(session_id)`
  - bad JSON / unknown type / missing sessionId → `None` (never raises)

### Modified: `spike/happy_bridge.py`
- `resolve_session_id(run, override=None, focused=None)`: priority
  `override` → `focused` → newest-active. (v1 signature gains `focused`.)
- Add a session summary lookup for ping text, sourced from the existing
  `list --active --json` output (id → `metadata.summary.text`).

### Modified: `spike/happy_llm.py`
- Accept a `voice_state` reference; pass `voice_state.focused_session_id` as
  `focused` into `resolve_session_id`.

### Modified: `spike/agent.py`
- On room connect: one `happy-agent list --active` call → seed
  `voice_state.focused_session_id` with the most-recently-active session (v1
  initial behavior preserved).
- `room.on("data_received", handler)`: `data_events.parse` → dispatch:
  - `FocusEvent` → update `voice_state.focused_session_id`.
  - `CompleteEvent` → if background (not the focused session), speak the ping;
    queue it if the agent is currently speaking.
  - `None` → ignore.

### App: `sources/realtime/RealtimeVoiceSession.tsx` (and `.web.tsx`)
- Add `sendStructuredMessage(payload: object)`:
  `publishData(new TextEncoder().encode(JSON.stringify(payload)), {reliable:true})`.

### App: `sources/realtime/hooks/voiceHooks.ts`
- `onSessionFocus`: also
  `getVoiceSession()?.sendStructuredMessage({type:'focused_session', sessionId})`.
- `onReady`: also
  `getVoiceSession()?.sendStructuredMessage({type:'session_complete', sessionId})`.

(These sit alongside the existing `sendContext`/`sendPrompt` calls; they do not
replace them. `types.ts` `VoiceSession` interface gains `sendStructuredMessage`.)

## Data flow (v2)

```
Phone navigates to Session A
  → voiceHooks.onSessionFocus(A)
  → publishData {type:'focused_session', sessionId:'A'}
  → Python data_received → voice_state.focused_session_id = A

User speaks "commit and push"
  → whisper STT → HappyBridgeLLM.chat
  → resolve_session_id(override=VOICE_SESSION_ID, focused=A)   # focused wins if no override
  → happy-agent send A "commit and push" --wait
  → happy-agent history A --limit N → reply → summarizer → Kokoro TTS → spoken

Background Session B finishes
  → voiceHooks.onReady(B)
  → publishData {type:'session_complete', sessionId:'B'}
  → Python data_received → B != focused → session.say("Your <B summary> session finished.")
```

**Ping summary text:** cache the `list --active --json` id→summary map, refresh on
focus events. Cache miss → generic "A background session finished."

## Error handling (v2)

- **Malformed data message** (bad JSON, unknown type, missing sessionId) → log +
  ignore. Handler never crashes.
- **`session_complete` for the focused session** → suppress the ping. The user is
  looking at it (and if they just spoke to it, v1 already speaks that reply). Ping
  **background** sessions only.
- **`session_complete` mid-turn** (agent speaking a reply) → queue, speak after
  current TTS finishes (avoid talk-over). A "speaking" flag / small deferral.
- **No focus ever received** → `resolve_session_id` falls back to
  `VOICE_SESSION_ID` → newest-active (v1 path, unchanged).
- **`focused_session` for a stale/dead id** → route there anyway; a failed
  `happy-agent send` surfaces as v1's spoken failure notice. No pre-validation.
- **Old APK still installed** (app change not yet deployed) → old app never sends
  the new message types → bridge falls back to newest-active. Graceful degrade.

## Testing

**Unit (pytest, stubbed subprocess — mirror v1 style, no live services):**
- `data_events.parse`: valid `focused_session` → FocusEvent; valid
  `session_complete` → CompleteEvent; bad JSON → None; unknown type → None;
  missing sessionId → None.
- `voice_state`: focus event updates `focused_session_id`; last-write wins.
- `resolve_session_id` priority: override > focused > newest-active; focused >
  newest-active with no override; newest-active when both None.
- Completion ping: background session → ping text from cached summary; focused
  session → suppressed; cache miss → generic text.
- Ping-while-speaking: queued when speaking, flushed on idle.

**Live (phone, real sessions):**
- Two active sessions A + B. Focus A, speak → routes to A. Focus B, speak →
  routes to B (no spray).
- Background completion: focus A, trigger long task in B, keep focus on A → hear
  "Your B session finished" ping while still routed to A.
- Ping suppressed for the focused session (no double-speak).
- Old-APK regression: app lacking new messages → voice still works (newest-active
  fallback).

**Regression:** v1's 17 tests stay green. Disable/re-enable voice (reconnect fix)
still works.

> `rtk` filters pytest output — read the real log at the path it prints
> (`~/.local/share/rtk/tee/*_pytest.log`).

## Non-goals

- Rebuilding session persistence, encryption, or lifecycle — Happy owns these.
- Voice-approve permissions (blocked; see Scope).

## Landmines carried from v1

- **Subagents are BLOCKED here** (haiku preflight → `401 safe-eu-models`). Execute
  the plan **inline** (executing-plans), not subagent-driven.
- Control/this-conversation session must never be targeted by voice.
- `send --wait` timeout is 180s in `happy_bridge._default_run`.
- App changes require an APK rebuild before live focus/ping testing on the phone;
  bridge-side work degrades gracefully until then.
