# Two-Tier Voice Bridge — Design

Date: 2026-07-09
Status: Approved (design), pending implementation plan

## Problem

The current voice bridge routes **every** spoken turn straight to a Claude Code
session and blocks on the full agent turn (`happy_bridge.send_and_wait`, timeout
180s) before speaking anything. Consequences:

- Every utterance — including chit-chat and clarifications — pays the full
  Claude Code latency (tens of seconds to minutes).
- The conversation freezes while Claude works; no natural back-and-forth.
- A lossy Ollama summary is spoken instead of a real conversational reply.

## Goal

A **two-tier** bridge:

1. A **fast local conversational layer** that talks with the user in real time.
2. **Deferred, non-blocking dispatch** to Claude Code only when the user has
   actually stated an actionable task — decided automatically by the fast layer.

The conversation never freezes; Claude runs in the background; answers are spoken
back when ready.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| When to dispatch to Claude | **Auto** — the fast local model classifies each turn (task vs chit-chat) and dispatches on a detected task. |
| Fast-layer model | **Local small LLM** via the existing Ollama (`qwen2.5:3b` today). Low latency, private, free. |
| Behavior while Claude works | **Brief ack on dispatch, then quiet.** Claude runs in the background; its answer is spoken when it returns. |
| Dispatch payload | **Distilled instruction + raw transcript** of everything said since the last dispatch. Nothing lost. |
| Concurrency | **One in-flight dispatch per target session ID.** Same session → queue. Different sessions → run in parallel. |

## Architecture

```
voice → STT (Whisper)
      → Conversational Front-End (local Ollama)   ── speaks immediate reply
          │  accumulates rolling transcript buffer
          │  classifies turn: chit-chat | actionable task
          └─[task]→ Dispatcher
                       builds payload = distilled instruction + raw buffer
                       resolves target session_id (focus-aware)
                       if session busy → enqueue; else → background dispatch
                       speaks brief ack, clears buffer
                              │
                              └─(background)→ happy_bridge.send_and_wait
                                              → fetch_last_reply
                                              → adaptive summarizer
                                              → session.say(answer, tagged with session)
```

### Components (each independently testable)

1. **Conversational front-end** — replaces the blocking behavior in
   `HappyBridgeLLM`. Per turn: (a) produce a short spoken reply via Ollama,
   (b) append the user text to the transcript buffer, (c) run the task
   classifier. Depends on: Ollama client, voice_state.

2. **Turn classifier** — a cheap per-turn Ollama call (or heuristic + model):
   returns `is_task: bool` and, if true, a `distilled_instruction`. Pure function
   of the current turn + recent buffer. Independently unit-testable with a
   mocked client.

3. **Dispatcher** — owns dispatch lifecycle. Resolves `session_id`
   (existing `resolve_session_id`, focus-aware). Maintains per-session state:
   `in_flight: set[session_id]` and `queues: dict[session_id, list[payload]]`.
   Fires background asyncio tasks. Never blocks the conversation.

4. **Answer delivery** — background task: on Claude completion, fetch reply,
   run `summarizer.summarize(reply, user_request)`, then `session.say()` the
   result, prefixed with the session tag when it is not the focused session
   (reuse existing summary/focus state). On the next queued item for that
   session, dispatch it.

5. **VoiceState (extended)** — add: transcript buffer, per-session in-flight
   set, per-session queue. Keep existing focus/summary fields.

## Data / State

- **Transcript buffer**: list of user utterances since last dispatch. Cleared on
  dispatch. Bounded (drop oldest beyond N turns to avoid unbounded growth).
- **Per-session in-flight**: `set[str]` of session IDs with a live Claude turn.
- **Per-session queue**: `dict[str, deque[Payload]]`. FIFO.
- **Payload**: `{session_id, instruction, transcript, user_request}`.

## Error handling

- **Claude dispatch fails / times out** → speak a short fallback
  ("Couldn't reach that session, check the chat"), drop the in-flight flag,
  process next queued item.
- **Ollama unavailable** (front-end or classifier) → degrade: skip the
  conversational reply, treat the turn as a task, send the **raw transcript**
  to Claude (never lose the user's instruction). Log the degradation.
- **Classifier false-negative** (missed a task) → user can restate; a future
  wake-phrase override is out of scope here.
- Handlers never crash the agent (existing invariant).

## Testing

Unit tests (mocked Ollama + mocked bridge, matching existing `spike/test_*.py`):

- Classifier: task vs chit-chat; distilled instruction extraction.
- Buffer: accumulation, clear-on-dispatch, bound enforcement.
- Dispatcher: same-session serialization (second task queued), different-session
  parallelism (both dispatched), queue drains in FIFO order on completion.
- Payload assembly: instruction + full raw transcript present.
- Answer delivery: summarizer called with user_request; session tag applied for
  non-focused sessions.
- Degradation: Ollama-down path sends raw transcript.

## Out of scope

- Wake-phrase / manual dispatch override.
- Streaming Claude output token-by-token.
- Endpointing / VAD tuning and Whisper silence-hallucination gating (separate
  backlog item, though related).
- Swapping the fast layer to a cloud or realtime model.

## Migration notes

- `HappyBridgeLLM` currently blocks and speaks a summary. It is refactored into
  the conversational front-end + dispatcher; the blocking `send_and_wait` moves
  into the background dispatch path.
- The adaptive summarizer (`summarize(reply, user_request)`) is reused unchanged.
- The immediate per-turn "On it." ack is already removed; the only ack now is the
  dispatch ack, which fires on real tasks only.
