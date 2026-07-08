# Voice → Claude Bridge v2 — Focus-Aware Sessions — Implementation Plan

**Date**: 2026-07-08
**Spec**: `docs/superpowers/specs/2026-07-08-voice-claude-bridge-v2-design.md`
**Branch**: `feat/voice-claude-bridge`
**Execute**: INLINE (subagents are blocked here; haiku preflight → 401 safe-eu-models).

## Order rationale

Server-side (box) work is fully testable without the phone and degrades
gracefully until the APK ships. The app change needs the box side present to
receive the messages. Build box-first, ship bridge-side, then ship the app.

Each phase is verifiable on its own. Do NOT move on until the phase's tests pass.

## Phase 1 — `voice_state.py` (new, shared state)

**Target:** `spike/voice_state.py`
**Change:** One tiny module holding the focused-session id and the session
summary cache. Plain object, single event loop, no locks.

```python
# spike/voice_state.py
class VoiceState:
    def __init__(self):
        self.focused_session_id = None
        self.summary_cache = {}   # {session_id: summary_text}

    def set_focus(self, session_id):
        self.focused_session_id = session_id

    def set_summary(self, session_id, text):
        if session_id:
            self.summary_cache[session_id] = text

    def get_summary(self, session_id):
        return self.summary_cache.get(session_id)
```

**Tests** (`spike/test_voice_state.py`):
- focus set → `focused_session_id == id`
- last-write-wins (set focus twice)
- summary cache set/get roundtrip
- `set_summary(None)` is a no-op (defensive, cache miss path)

**Verify:** `python -m pytest spike/test_voice_state.py` (read the rtk log).

## Phase 2 — `data_events.py` (new, parser)

**Target:** `spike/data_events.py`
**Change:** Isolated parser. The ONLY place that knows the wire format.

```python
# spike/data_events.py
import json
from dataclasses import dataclass

@dataclass
class FocusEvent:
    session_id: str

@dataclass
class CompleteEvent:
    session_id: str

def parse(raw: bytes) -> FocusEvent | CompleteEvent | None:
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    t = payload.get("type")
    sid = payload.get("sessionId")
    if not isinstance(sid, str) or not sid:
        return None
    if t == "focused_session":
        return FocusEvent(session_id=sid)
    if t == "session_complete":
        return CompleteEvent(session_id=sid)
    return None
```

**Tests** (`spike/test_data_events.py`):
- valid focused_session → FocusEvent
- valid session_complete → CompleteEvent
- bad JSON → None
- valid JSON, unknown type → None
- missing sessionId → None
- empty sessionId → None
- non-dict JSON (e.g. `[1,2]`) → None
- bytes input (the real data-channel type)

**Verify:** `python -m pytest spike/test_data_events.py`.

## Phase 3 — `happy_bridge.py` (modified)

**Target:** `spike/happy_bridge.py`
**Change:**
1. `resolve_session_id(run, override=None, focused=None)` — priority
   `override → focused → newest-active`. New `focused` kwarg.
2. New helper `active_sessions_with_summary(run)` returning `[{id, summary}]`
   parsed from `list --active --json`, reading `metadata.summary.text` (or
   `""` when absent). Used by agent.py to seed/refresh
   `voice_state.summary_cache`. Keep `_default_run`, `check_auth`,
   `send_and_wait`, `_agent_text_event`, `fetch_last_reply` unchanged.

**Tests** (`spike/test_happy_bridge.py`, extend):
- `resolve_session_id(focused="F")` with no override → "F"
- `override > focused` (both given) → override
- `focused > newest-active` (no override) → focused
- `newest-active` when both None → newest
- `active_sessions_with_summary` parses `metadata.summary.text`, missing → ""

Keep all existing v1 tests green (regression).

**Verify:** `python -m pytest spike/test_happy_bridge.py`.

## Phase 4 — `happy_llm.py` (modified)

**Target:** `spike/happy_llm.py`
**Change:**
- `HappyBridgeLLM.__init__` accepts `voice_state=None`.
- `_HappyStream._blocking_bridge` calls
  `self._llm_impl._resolve_session(override=impl._session_override,
  focused=(impl._voice_state.focused_session_id if impl._voice_state else None))`.
- Backwards compat: existing tests construct `HappyBridgeLLM` without
  `voice_state` and with `resolve_session=lambda override=None: ...`. Keep the
  signature compatible: `resolve_session` MUST accept both `override=None` and
  `focused=None` kwargs. The two existing tests use `lambda override=None` and
  `lambda override=None: ...` — these don't accept `focused`. Change the bridge
  to call `resolve_session(override=True, focused=True)` kwarg-style. Update
  the two existing happy_llm tests' `resolve_session` lambdas to accept
  `focused=None` so they don't crash. This is editing MY tests, not the user's
  tests' assertions.

**Tests** (`spike/test_happy_llm.py`, extend):
- new test: pass a `VoiceState` with focused="F", resolve returns "F" when
  override is None.
- new test: override wins over focused.
- keep existing 4 tests green (two need their lambda signature widened).

**Verify:** `python -m pytest spike/test_happy_llm.py`.

## Phase 5 — `agent.py` wiring (modified)

**Target:** `spike/agent.py`
**Change:**
1. Import `voice_state`, `data_events`.
2. Create `state = voice_state.VoiceState()` in `entrypoint`, pass it into
   `HappyBridgeLLM(..., voice_state=state)`.
3. On room connect: call `happy_bridge.active_sessions_with_summary()` → seed
   `state.summary_cache` and set `state.focused_session_id` to the
   most-recently-active session's id if not already focused (v1 initial
   behaviour). Wrap in try/except — never crash the agent on a list failure.
4. `ctx.room.on("data_received", handler)`:
   - `ev = data_events.parse(raw)`
   - `FocusEvent` → `state.set_focus(ev.session_id)`; also refresh
     `state.summary_cache` from a fresh `active_sessions_with_summary` (cheap,
     on focus only).
   - `CompleteEvent` → if `ev.session_id == state.focused_session_id`: skip
     (suppress); else build the ping text: `state.get_summary(sid)` or
     fallback "A background session finished." → `await session.say(ping)`.
     If the agent is currently speaking the queue already serializes `say`
     calls in LiveKit's AgentSession, so no extra deferral in v2 (the spec
     mentions a deferral but `say` is already queued on the session — keep it
     simple; revisit if talk-over is observed live).
   - `None` → ignore.
5. Wrap the whole handler in try/except, log and ignore on any failure. The
   handler NEVER crashes the agent.

**No unit test here** — agent.py wiring is hard to unit test (live room,
models). Verify by code review + live run. The logic it depends on
(voice_state, data_events, resolve_session_id priority) is already unit-tested
in phases 1-4.

**Verify:** full pytest sweep green; then live start
(`systemctl --user restart voice-agent; journalctl --user -u voice-agent -f`)
confirms "Voice bridge live" greeting + no traceback.

## Phase 6 — App side (Happy app, separate repo)

**Target:** `~/happy-src/packages/happy-app/...`
**Change:** Per spec §"App".
- `sources/realtime/RealtimeVoiceSession.tsx` (+ `.web.tsx`): add
  `sendStructuredMessage(payload: object)` →
  `this.publishData(new TextEncoder().encode(JSON.stringify(payload)),
  {reliable:true})`.
- `types.ts`: add `sendStructuredMessage` to the `VoiceSession` interface.
- `sources/realtime/hooks/voiceHooks.ts`:
  - `onSessionFocus(id)`: also
    `getVoiceSession()?.sendStructuredMessage({type:'focused_session', sessionId:id})`.
  - `onReady(id)`: also
    `getVoiceSession()?.sendStructuredMessage({type:'session_complete', sessionId:id})`.
- APK rebuild + deploy to phone.

This phase is NOT executed now — it's app-side work requiring a build. The box
degrades gracefully until then (no focus msgs → newest-active fallback, same as
v1). Land the box side first.

## Phase 7 — Live verification (box only, pre-APK)

**With the box shipped but no new APK yet**, verify graceful degrade:
- `VOICE_SESSION_ID` still pins (v1 behaviour).
- No focus messages arrive → `resolve_session_id` falls back to
  `override → newest-active`.
- Full pytest suite green (v1 17 + new v2 tests).

**Post-APK live** (deferred to a later session once Phase 6 is done):
- Two sessions A+B, focus A, speak → routes to A.
- Focus B, speak → routes to B (no spray).
- Background completion → heard a ping.
- Focused completion → no ping (no double-speak).
- Old-APK regression → still works.

## Phase 8 — Cleanup (LAST, only after the box-side works)

- Grep for leftover TODOs / placeholders in the v2 files.
- Run ruff/black if the repo uses it (check existing config).
- Commit per phase, conventional-commit style matching history (`feat(voice): …`).
- Progress ledger update (`.superpowers/sdd/progress.md` — git-ignored scratch).

## Risks / landmines (carried from spec)
- Subagents BLOCKED → everything inline.
- Control/this session never targeted by voice.
- `send --wait` timeout 180s.
- App changes need APK rebuild before live focus/ping testing.
- rtk filters pytest output → read `~/.local/share/rtk/tee/*_pytest.log`.