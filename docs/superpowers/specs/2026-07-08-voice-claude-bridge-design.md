# Voice → Claude Code Bridge (via Happy) — Design

**Date**: 2026-07-08
**Status**: Approved for planning
**Working dir**: `/home/hyggan/voice-agent`

## Problem

The local voice spike currently runs a conversation-only agent: whisper STT →
`qwen2.5:3b` (ollama) → Kokoro TTS. The local LLM can *talk about* doing work
but has no ability to *do* anything — no tools, no file access, no git/PR.

The user wants to speak requests ("commit the changes and open a PR") and have a
real coding agent execute them, then hear a summary back. The real coding agent
is **Claude Code**, already wired into the **Happy** app with session management,
persistence, and end-to-end encryption.

**Goal**: make the voice layer a *pipe* to an existing Claude Code session. Do not
rebuild persistence, session state, or encryption — Happy already owns all of it.

## Key findings (from Happy source, `~/happy-src`)

1. **The message funnel**: typed chat (`SessionView.tsx:550`, `source:'chat'`) and
   voice (`realtimeClientTools.ts:34`, `source:'voice'`) both converge on
   `sync.sendMessage(sessionId, text, options)` (`sync/sync.ts:568`). It encrypts
   with per-session keys (client-side) and ships over the sync websocket to
   happy-server, which delivers to the running Claude Code session.

2. **Machine-local funnel** — `happy-agent` (package `happy-agent`, "CLI client for
   controlling Happy Coder agents remotely") authenticates as the user, handles
   encryption, and hits the same server-side path *without the phone*:
   - `happy-agent list --active --json` — list/enumerate active sessions
   - `happy-agent send <sessionId> "<text>" --wait` — inject a message,
     block until the agent turn completes (`client.waitForTurnCompletion()`,
     `index.ts:389`)
   - `happy-agent history <sessionId> --limit N --json` — read messages back
     (`index.ts:416`); `send --wait` does **not** print the reply, so the reply
     is retrieved via `history`
   - `happy-agent status <sessionId>` — live session state

3. **Completion + focus signals** (for v2):
   - Per-session `agentState`, `thinking`, `thinkingAt` (`storageTypes.ts:156-159`)
     — `thinking → false` is the task-complete signal, detectable via
     `happy-agent status` or the app's sync store.
   - `sendContextualUpdate` (`realtimeClientTools.ts:38`, `types.ts:15`) — the app
     can silently inject context ("background session finished") into a voice
     session.
   - **Focus / tab-swap is phone-only knowledge** — UI navigation state, not
     visible to a server-side process. This is the crux that shapes v2.

## Architecture

### Phase 1 (v1) — server-side pipe (Route A)

All on the box. No app changes, no APK rebuild. Ships immediately for testing.

The LiveKit Python agent (`spike/agent.py`) stops being a brain and becomes a pipe:

```
phone mic → LiveKit room → whisper STT (final transcript)
   → happy-agent send <sid> "<text>" --wait       (inject into Claude session)
   → happy-agent history <sid> --limit 1 --json    (read Claude's reply)
   → local summarizer (ollama, conservative + verbose)
   → Kokoro TTS → back into the room (spoken)
```

Components and responsibilities:

- **STT (whisper)** — unchanged from current spike. Produces final transcripts.
- **Bridge (new)** — replaces the `openai.LLM(ollama)` brain in the AgentSession.
  On each finalized user turn:
  1. Resolve the target session id (see Defaults).
  2. `happy-agent send <sid> "<transcript>" --wait` (subprocess).
  3. `happy-agent history <sid> --limit 1 --json`, parse the last assistant
     message text.
  4. If the session is blocked on a permission request instead of producing a
     reply, speak the permission notice (see Defaults).
  5. Hand the reply text to the summarizer.
- **Summarizer (ollama, retained ONLY for this)** — compresses Claude's reply to a
  verbose-but-spoken summary. Prompt is near-extractive: *summarize only what is
  stated, never add facts; if unsure, say "check the chat for details."* The full
  reply is already in the phone chat, so the spoken summary is a lossy preview by
  design, not the source of truth.
- **TTS (Kokoro)** — unchanged. Speaks the summary back into the room.

No persistence, no session store, no encryption code in the agent — delegated to
`happy-agent`.

#### v1 Defaults

- **Session target**: most-recently-active session (`happy-agent list --active`,
  newest). Overridable by a fixed session id in config.
- **Auth prerequisite**: `happy-agent auth login` (QR) must be run once on the box.
  The agent checks for credentials at startup and speaks a clear error if missing.
- **Forwarding**: every finalized transcript, while voice is on, is forwarded to
  Claude. No wake-word gate in v1 (add later if it over-triggers).
- **Permissions**: if Claude blocks on a permission request (e.g., before a push),
  v1 **detects** it (session state shows a pending request / no reply) and
  **speaks** "Claude needs permission for X — approve in the app." No voice-approve,
  no `--yolo` in v1. Voice-approve is deferred to v2.

### Phase 2 (v2) — focus-aware multi-session (Route B)

Starts immediately after v1 lands, because the app-side changes carry a long build
lead time. Delivers the desired behavior: a light completion ping when any
background task finishes, and a full spoken summary only when the user *swaps to
that session's tab*.

Because focus is phone-only knowledge, v2 requires the app to participate — either:
- **App-driven** (mirror the existing ElevenLabs integration but with our local
  STT/TTS/summarizer): the app already tracks focus + agent-state and has
  `sendContextualUpdate`; the focus-trigger comes almost for free; or
- **Focus channel**: keep the server-side agent and add a phone→agent signal
  (e.g., over the LiveKit data channel) carrying focused-session id and
  agent-state transitions.

v2 scope:
- Completion ping across all active sessions (`thinking → false`), spoken as a
  one-liner regardless of focus.
- Focus / tab-swap signal → triggers a summary of *that* session's latest output.
- Voice-approve permissions via the `processPermissionRequest` path.

Route choice (app-driven vs focus channel) is decided at the start of v2 planning,
not here.

## Data flow (v1)

```
User speaks
  → LiveKit room (phone ↔ local livekit-server)
  → Python agent: whisper STT → final transcript
  → subprocess: happy-agent send <sid> --wait
      → happy-server → Claude Code session (does the work; reply persisted by Happy)
  → subprocess: happy-agent history <sid> --limit 1 --json → reply text
  → ollama summarizer → spoken summary text
  → Kokoro TTS → LiveKit room → phone speaker
Full reply visible in the Happy chat on the phone (authoritative).
```

## Error handling (v1)

- **No credentials**: startup check fails → speak "Voice bridge not authenticated,
  run happy-agent auth login on the host."
- **No active session**: `list --active` empty → speak "No active Claude session
  found."
- **`happy-agent send` non-zero exit / timeout**: speak a short failure notice; log
  full stderr to the journal. Do not crash the agent.
- **Permission block**: detect pending request, speak the permission notice, do not
  hang.
- **Summarizer failure**: fall back to speaking a truncated raw reply (first N
  sentences) rather than nothing.
- Reuse the existing reconnect fix (agent leaves + deletes room on participant
  disconnect) so disable/re-enable keeps working.

## Testing

- **Unit**: stub `happy-agent` (fake subprocess) and exercise the
  transcript → send → history → summarize → TTS chain, including the error paths
  (no creds, no session, send failure, permission block, summarizer failure).
- **Live**: end-to-end from the phone against a real active Claude session —
  speak a request, confirm Claude executes and a summary is spoken; confirm the
  full reply appears in the Happy chat.
- **Regression**: disable/re-enable voice repeatedly (reconnect fix).

## Out of scope (v1)

- Focus-aware multi-session orchestration (→ v2).
- Voice-approving permission requests (→ v2).
- Wake-word gating (optional, later).
- iOS voice-with-screen-locked (`UIBackgroundModes`) — pre-existing deferred item.

## Non-goals

- Rebuilding session persistence, encryption, or session lifecycle — Happy owns
  these; the bridge must never duplicate them.
