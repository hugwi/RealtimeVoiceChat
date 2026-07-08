# Voice → Claude Bridge (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the local voice spike into a pipe that forwards spoken requests to an existing Claude Code session (via Happy's `happy-agent` CLI) and speaks back a conservative summary of Claude's reply.

**Architecture:** The LiveKit `AgentSession` keeps whisper STT and Kokoro TTS but its "brain" is replaced by a custom `LLM` implementation. On each user turn the custom LLM shells out to `happy-agent send <sid> --wait`, reads Claude's reply with `happy-agent history`, summarizes it with a local ollama model (conservative, near-extractive), and emits that summary as the assistant turn — which Kokoro speaks. No persistence, sessions, or encryption live in the agent; `happy-agent`/Happy own all of it.

**Tech Stack:** Python 3.11 (existing venv), livekit-agents 1.6.4, faster-whisper, Kokoro TTS, ollama (`qwen2.5:3b`) via OpenAI-compatible API, Node `happy-agent` CLI, pytest.

## Global Constraints

- Working dir: `/home/hyggan/voice-agent`; run everything inside the existing venv (`source venv/bin/activate`).
- Live service copy is `~/voice-agent/spike/` (NOT `happy-src/voice-agent/`). Systemd user units: `voice-agent`, `voice-livekit`, `voice-token`.
- Do NOT rebuild persistence, session lifecycle, or encryption — delegate to `happy-agent`.
- `happy-agent` credentials live at `~/.happy/agent.key`. If absent, the bridge must fail gracefully (speak an error), never crash-loop.
- Summarizer prompt is near-extractive: summarize only what is stated, never invent facts, say "check the chat for details" when unsure.
- Keep the existing reconnect fix in `agent.py` (delete room on `participant_disconnected`) intact.
- Session selection default: most-recently-active session (max `activeAt`). Override via env `VOICE_SESSION_ID`.
- `happy-agent` invocation is via the wrapper `~/voice-agent/bin/happy-agent`; override with env `HAPPY_AGENT_BIN`.

---

### Task 1: happy-agent available, authed, and smoke-tested

**Files:**
- Create: `/home/hyggan/voice-agent/bin/happy-agent` (wrapper script)

**Interfaces:**
- Produces: a runnable `~/voice-agent/bin/happy-agent` that forwards args to the built CLI; a confirmed active session id for live testing later.

- [ ] **Step 1: Build the happy-agent CLI**

Run:
```bash
cd /home/hyggan/happy-src/packages/happy-agent && pnpm build
```
Expected: completes without error; `dist/` is created and `bin/happy-agent.mjs` exists.

- [ ] **Step 2: Create the wrapper script**

Create `/home/hyggan/voice-agent/bin/happy-agent`:
```bash
#!/usr/bin/env bash
exec node /home/hyggan/happy-src/packages/happy-agent/bin/happy-agent.mjs "$@"
```
Then:
```bash
chmod +x /home/hyggan/voice-agent/bin/happy-agent
```

- [ ] **Step 3: Authenticate (MANUAL — human step)**

Run:
```bash
/home/hyggan/voice-agent/bin/happy-agent auth login
```
Scan the QR code with the Happy app on the phone. This writes `~/.happy/agent.key`.
Verify:
```bash
test -f ~/.happy/agent.key && echo "authed" || echo "NOT authed"
```
Expected: `authed`.

- [ ] **Step 4: Smoke-test session listing**

Run:
```bash
/home/hyggan/voice-agent/bin/happy-agent list --active --json
```
Expected: a JSON array; each element has `id`, `seq`, `createdAt`, `updatedAt`, `active`, `activeAt`. Note one active session id for the live test in Task 5. If the array is empty, start/resume a Claude session in Happy first.

- [ ] **Step 5: Commit**

```bash
cd /home/hyggan/voice-agent
git add bin/happy-agent
git commit -m "feat(voice): add happy-agent wrapper for voice bridge"
```

---

### Task 2: happy_bridge.py — happy-agent subprocess wrappers

**Files:**
- Create: `/home/hyggan/voice-agent/spike/happy_bridge.py`
- Test: `/home/hyggan/voice-agent/spike/test_happy_bridge.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `class HappyAgentError(Exception)`
  - `check_auth() -> bool`
  - `resolve_session_id(run=..., override: str | None = None) -> str`
  - `send_and_wait(session_id: str, text: str, run=...) -> None`
  - `fetch_last_reply(session_id: str, run=...) -> str`
  - `run` is a callable `(args: list[str]) -> str` returning stdout; the default runs the wrapper via subprocess and raises `HappyAgentError` on non-zero exit. Tests inject a fake `run`.

- [ ] **Step 1: Ensure pytest is available**

Run:
```bash
cd /home/hyggan/voice-agent && source venv/bin/activate && python -c "import pytest" 2>/dev/null || pip install pytest
```
Expected: no error (pytest importable).

- [ ] **Step 2: Write the failing tests**

Create `/home/hyggan/voice-agent/spike/test_happy_bridge.py`:
```python
import json
import pytest
import happy_bridge as hb


def test_resolve_session_id_uses_override():
    def run(args):
        raise AssertionError("run should not be called when override given")
    assert hb.resolve_session_id(run=run, override="sess-123") == "sess-123"


def test_resolve_session_id_picks_newest_active():
    sessions = [
        {"id": "old", "activeAt": 100, "updatedAt": 100},
        {"id": "new", "activeAt": 500, "updatedAt": 200},
        {"id": "mid", "activeAt": 300, "updatedAt": 900},
    ]
    def run(args):
        assert args == ["list", "--active", "--json"]
        return json.dumps(sessions)
    assert hb.resolve_session_id(run=run) == "new"


def test_resolve_session_id_raises_when_none():
    def run(args):
        return "[]"
    with pytest.raises(hb.HappyAgentError):
        hb.resolve_session_id(run=run)


def test_send_and_wait_invokes_send_with_wait():
    calls = []
    def run(args):
        calls.append(args)
        return ""
    hb.send_and_wait("sid1", "commit and push", run=run)
    assert calls == [["send", "sid1", "commit and push", "--wait"]]


def test_fetch_last_reply_extracts_nested_text():
    messages = [
        {"content": {"role": "user", "content": "commit and push"}},
        {"content": {"role": "agent", "content": {"type": "text", "text": "Committed and opened PR #12."}}},
    ]
    def run(args):
        assert args[0] == "history"
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == "Committed and opened PR #12."


def test_fetch_last_reply_handles_string_content():
    messages = [
        {"content": {"role": "agent", "content": "Done."}},
    ]
    def run(args):
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == "Done."


def test_fetch_last_reply_skips_trailing_user_message():
    messages = [
        {"content": {"role": "agent", "content": {"type": "text", "text": "All set."}}},
        {"content": {"role": "user", "content": "thanks"}},
    ]
    def run(args):
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == "All set."


def test_fetch_last_reply_empty_when_no_agent_message():
    def run(args):
        return "[]"
    assert hb.fetch_last_reply("sid1", run=run) == ""
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
cd /home/hyggan/voice-agent/spike && python -m pytest test_happy_bridge.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'happy_bridge'`.

- [ ] **Step 4: Write the implementation**

Create `/home/hyggan/voice-agent/spike/happy_bridge.py`:
```python
"""Thin wrappers around the happy-agent CLI. No persistence lives here —
happy-agent (and Happy) own sessions, encryption, and history."""
import json
import os
import subprocess

HAPPY_AGENT_BIN = os.environ.get(
    "HAPPY_AGENT_BIN", "/home/hyggan/voice-agent/bin/happy-agent"
)
AGENT_KEY_PATH = os.path.expanduser("~/.happy/agent.key")
_HISTORY_SCAN = 8  # how many recent messages to scan for the last agent reply


class HappyAgentError(Exception):
    pass


def _default_run(args):
    """Run happy-agent with args, return stdout, raise on failure."""
    try:
        proc = subprocess.run(
            [HAPPY_AGENT_BIN, *args],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise HappyAgentError(f"happy-agent call failed: {e}") from e
    if proc.returncode != 0:
        raise HappyAgentError(
            f"happy-agent {args!r} exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def check_auth():
    """True if happy-agent credentials are present on this box."""
    return os.path.isfile(AGENT_KEY_PATH)


def resolve_session_id(run=_default_run, override=None):
    """Return the target session id: the override if given, else the
    most-recently-active session (max activeAt)."""
    if override:
        return override
    sessions = json.loads(run(["list", "--active", "--json"]))
    if not sessions:
        raise HappyAgentError("no active Claude session found")
    sessions.sort(
        key=lambda s: s.get("activeAt") or s.get("updatedAt") or 0,
        reverse=True,
    )
    return sessions[0]["id"]


def send_and_wait(session_id, text, run=_default_run):
    """Send a message to the session and block until the agent turn completes."""
    run(["send", session_id, text, "--wait"])


def _extract_text(message):
    """Pull assistant text out of a happy-agent history message, or ''."""
    content = message.get("content")
    if not isinstance(content, dict):
        return ""
    if content.get("role") == "user":
        return ""
    inner = content.get("content")
    if isinstance(inner, dict):
        return (inner.get("text") or "").strip()
    if isinstance(inner, str):
        return inner.strip()
    return ""


def fetch_last_reply(session_id, run=_default_run):
    """Return the text of the most recent non-user message, or '' if none."""
    messages = json.loads(
        run(["history", session_id, "--limit", str(_HISTORY_SCAN), "--json"])
    )
    for message in reversed(messages):
        text = _extract_text(message)
        if text:
            return text
    return ""
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd /home/hyggan/voice-agent/spike && python -m pytest test_happy_bridge.py -v
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/hyggan/voice-agent
git add spike/happy_bridge.py spike/test_happy_bridge.py
git commit -m "feat(voice): happy-agent bridge wrappers with tests"
```

---

### Task 3: summarizer.py — conservative reply summarizer

**Files:**
- Create: `/home/hyggan/voice-agent/spike/summarizer.py`
- Test: `/home/hyggan/voice-agent/spike/test_summarizer.py`

**Interfaces:**
- Consumes: nothing (leaf module). Uses an injected OpenAI-compatible client in tests.
- Produces:
  - `summarize(reply: str, *, client=None, model: str = "qwen2.5:3b") -> str`
  - `SYSTEM_PROMPT: str`
  - When `reply` is blank returns a fixed "nothing to report" string; on client error falls back to a truncated raw reply (never raises).

- [ ] **Step 1: Write the failing tests**

Create `/home/hyggan/voice-agent/spike/test_summarizer.py`:
```python
import summarizer as s


class _FakeMessage:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _FakeCompletions:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return type("R", (), {"choices": [_FakeMessage(self._content)]})


class _FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = type("C", (), {"completions": _FakeCompletions(content, error)})


def test_summarize_returns_model_output():
    client = _FakeClient(content="Committed and opened PR 12.")
    assert s.summarize("long claude reply", client=client) == "Committed and opened PR 12."


def test_summarize_blank_reply_returns_placeholder():
    client = _FakeClient(content="should not be used")
    out = s.summarize("   ", client=client)
    assert "check the chat" in out.lower() or "nothing" in out.lower()


def test_summarize_falls_back_to_truncation_on_error():
    reply = "First sentence. Second sentence. Third sentence. Fourth sentence."
    client = _FakeClient(error=RuntimeError("ollama down"))
    out = s.summarize(reply, client=client)
    assert out.startswith("First sentence.")
    assert "Fourth sentence." not in out


def test_summarize_never_raises_on_empty_model_output():
    reply = "Alpha. Beta. Gamma."
    client = _FakeClient(content="")
    out = s.summarize(reply, client=client)
    assert out.startswith("Alpha.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/hyggan/voice-agent/spike && python -m pytest test_summarizer.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'summarizer'`.

- [ ] **Step 3: Write the implementation**

Create `/home/hyggan/voice-agent/spike/summarizer.py`:
```python
"""Summarize a Claude reply into a spoken-friendly, near-extractive summary.
The full reply is always visible in the Happy chat, so this is a lossy preview
by design — but it must never fabricate facts."""
import re

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"
DEFAULT_MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = (
    "You turn a coding agent's reply into a short spoken summary. "
    "Summarize ONLY what is stated. Never add facts, numbers, or names that "
    "are not present. If the reply is unclear, say 'Check the chat for details.' "
    "Keep it to two or three sentences, plain spoken English, no markdown."
)

_PLACEHOLDER = "Nothing to report. Check the chat for details."


def _default_client():
    from openai import OpenAI

    return OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)


def _truncate(text, max_sentences=3):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:max_sentences]).strip()


def summarize(reply, *, client=None, model=DEFAULT_MODEL):
    if not reply or not reply.strip():
        return _PLACEHOLDER
    if client is None:
        client = _default_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": reply},
            ],
            temperature=0.2,
        )
        out = (resp.choices[0].message.content or "").strip()
    except Exception:
        out = ""
    if not out:
        return _truncate(reply)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/hyggan/voice-agent/spike && python -m pytest test_summarizer.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/hyggan/voice-agent
git add spike/summarizer.py spike/test_summarizer.py
git commit -m "feat(voice): conservative reply summarizer with tests"
```

---

### Task 4: happy_llm.py — custom LiveKit LLM wiring bridge + summarizer

**Files:**
- Create: `/home/hyggan/voice-agent/spike/happy_llm.py`
- Test: `/home/hyggan/voice-agent/spike/test_happy_llm.py`

**Interfaces:**
- Consumes: `happy_bridge.HappyAgentError` (semantics), and callables shaped like `happy_bridge.resolve_session_id`, `happy_bridge.send_and_wait`, `happy_bridge.fetch_last_reply`, `summarizer.summarize`.
- Produces:
  - `class HappyBridgeLLM(livekit.agents.llm.LLM)` constructed with keyword callables:
    `HappyBridgeLLM(*, resolve_session, send_and_wait, fetch_last_reply, summarize, session_override=None)`
  - `.chat(*, chat_ctx, tools=None, conn_options=..., ...) -> LLMStream` emits exactly one assistant `ChatChunk` whose `delta.content` is the spoken summary (or a spoken error string on `HappyAgentError`).

- [ ] **Step 1: Write the failing tests**

Create `/home/hyggan/voice-agent/spike/test_happy_llm.py`:
```python
import asyncio
from livekit.agents.llm import ChatContext
import happy_bridge as hb
import happy_llm


def _collect(stream):
    async def run():
        chunks = []
        async for chunk in stream:
            if chunk.delta and chunk.delta.content:
                chunks.append(chunk.delta.content)
        return "".join(chunks)
    return asyncio.run(run())


def _ctx(user_text):
    ctx = ChatContext.empty()
    ctx.add_message(role="user", content=user_text)
    return ctx


def test_happy_llm_speaks_summary_of_reply():
    calls = {}
    llm = happy_llm.HappyBridgeLLM(
        resolve_session=lambda override=None: "sid1",
        send_and_wait=lambda sid, text: calls.setdefault("sent", (sid, text)),
        fetch_last_reply=lambda sid: "Committed everything and opened PR 12.",
        summarize=lambda reply: "Committed and opened a PR.",
    )
    out = _collect(llm.chat(chat_ctx=_ctx("commit and open a PR")))
    assert calls["sent"] == ("sid1", "commit and open a PR")
    assert out == "Committed and opened a PR."


def test_happy_llm_speaks_error_on_happy_agent_failure():
    def boom(override=None):
        raise hb.HappyAgentError("no active Claude session found")
    llm = happy_llm.HappyBridgeLLM(
        resolve_session=boom,
        send_and_wait=lambda sid, text: None,
        fetch_last_reply=lambda sid: "",
        summarize=lambda reply: "unused",
    )
    out = _collect(llm.chat(chat_ctx=_ctx("do something")))
    assert "session" in out.lower()


def test_happy_llm_uses_session_override():
    seen = {}
    llm = happy_llm.HappyBridgeLLM(
        resolve_session=lambda override=None: seen.setdefault("override", override) or "resolved",
        send_and_wait=lambda sid, text: seen.setdefault("sid", sid),
        fetch_last_reply=lambda sid: "ok",
        summarize=lambda reply: "ok spoken",
        session_override="forced-sid",
    )
    _collect(llm.chat(chat_ctx=_ctx("hi")))
    assert seen["override"] == "forced-sid"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /home/hyggan/voice-agent/spike && python -m pytest test_happy_llm.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'happy_llm'`.

- [ ] **Step 3: Write the implementation**

Create `/home/hyggan/voice-agent/spike/happy_llm.py`:
```python
"""A LiveKit LLM whose 'completion' is: forward the user's turn to a Claude
Code session via happy-agent, then speak a summary of Claude's reply."""
import asyncio
import uuid

from livekit.agents.llm import LLM, LLMStream, ChatChunk, ChoiceDelta

from happy_bridge import HappyAgentError


def _last_user_text(chat_ctx):
    for item in reversed(chat_ctx.items):
        if getattr(item, "role", None) != "user":
            continue
        content = getattr(item, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [p for p in content if isinstance(p, str)]
            if parts:
                return " ".join(parts).strip()
    return ""


class HappyBridgeLLM(LLM):
    def __init__(self, *, resolve_session, send_and_wait, fetch_last_reply,
                 summarize, session_override=None):
        super().__init__()
        self._resolve_session = resolve_session
        self._send_and_wait = send_and_wait
        self._fetch_last_reply = fetch_last_reply
        self._summarize = summarize
        self._session_override = session_override

    def chat(self, *, chat_ctx, tools=None, conn_options=None, **kwargs):
        user_text = _last_user_text(chat_ctx)
        return _HappyStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            user_text=user_text,
        )


class _HappyStream(LLMStream):
    def __init__(self, llm, *, chat_ctx, tools, conn_options, user_text):
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._llm_impl = llm
        self._user_text = user_text

    def _blocking_bridge(self):
        impl = self._llm_impl
        session_id = impl._resolve_session(override=impl._session_override)
        impl._send_and_wait(session_id, self._user_text)
        reply = impl._fetch_last_reply(session_id)
        return impl._summarize(reply)

    async def _run(self):
        try:
            spoken = await asyncio.get_event_loop().run_in_executor(
                None, self._blocking_bridge
            )
        except HappyAgentError as e:
            spoken = f"Sorry, I couldn't reach the coding session: {e}."
        self._event_ch.send_nowait(
            ChatChunk(
                id=str(uuid.uuid4()),
                delta=ChoiceDelta(role="assistant", content=spoken),
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/hyggan/voice-agent/spike && python -m pytest test_happy_llm.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/hyggan/voice-agent
git add spike/happy_llm.py spike/test_happy_llm.py
git commit -m "feat(voice): custom LiveKit LLM bridging to Claude via happy-agent"
```

---

### Task 5: Wire the bridge into agent.py and live-test

**Files:**
- Modify: `/home/hyggan/voice-agent/spike/agent.py`

**Interfaces:**
- Consumes: `happy_llm.HappyBridgeLLM`, `happy_bridge` (resolve/send/fetch/check_auth), `summarizer.summarize`.
- Produces: a running `voice-agent` service that pipes voice → Claude → spoken summary.

- [ ] **Step 1: Replace the LLM brain and greeting in `entrypoint`**

In `/home/hyggan/voice-agent/spike/agent.py`, replace the current `entrypoint` body (the `session = AgentSession(...)`, `session.start(...)`, and `session.generate_reply(...)` block) so the session uses the bridge LLM, greets without hitting Claude, and checks auth first. The final `entrypoint` reads:

```python
async def entrypoint(ctx: JobContext):
    await ctx.connect()

    # When the user leaves (e.g. disables voice), delete the room so this job's
    # agent leaves AND the room is torn down. LiveKit only auto-dispatches a job
    # on room *creation*, so a lingering empty room would let the user re-join
    # the same room with no fresh agent — silence. Deleting it forces the next
    # connection to create a new room, which dispatches a new job.
    def _on_participant_disconnected(participant: rtc.RemoteParticipant):
        ctx.delete_room()

    ctx.room.on("participant_disconnected", _on_participant_disconnected)

    session = AgentSession(
        stt=WhisperSTT(model=ctx.proc.userdata["whisper"]),
        llm=happy_llm.HappyBridgeLLM(
            resolve_session=happy_bridge.resolve_session_id,
            send_and_wait=happy_bridge.send_and_wait,
            fetch_last_reply=happy_bridge.fetch_last_reply,
            summarize=summarizer.summarize,
            session_override=os.environ.get("VOICE_SESSION_ID") or None,
        ),
        tts=KokoroTTS(pipeline=ctx.proc.userdata["kokoro"]),
    )
    await session.start(
        agent=Agent(instructions="You are a voice bridge to a Claude Code session."),
        room=ctx.room,
    )

    if not happy_bridge.check_auth():
        await session.say(
            "Voice bridge is not authenticated. Run happy-agent auth login on the host."
        )
        return

    await session.say("Voice bridge live. What should Claude do?")
```

- [ ] **Step 2: Update imports at the top of `agent.py`**

Add these imports near the existing imports and remove the now-unused ollama LLM plugin import. Specifically add:
```python
import os

import happy_bridge
import happy_llm
import summarizer
```
And delete the line:
```python
from livekit.plugins import openai
```
(The `OLLAMA_MODEL` constant is no longer used by `agent.py`; the summarizer owns its own model constant. Leaving the constant is harmless, but remove the `openai` import since it is now unused.)

- [ ] **Step 3: Sanity-check the module imports**

Run:
```bash
cd /home/hyggan/voice-agent/spike && source ../venv/bin/activate && python -c "import agent; print('agent imports OK')"
```
Expected: prints `agent imports OK` with no ImportError. (Model loading logs may appear; that is fine.)

- [ ] **Step 4: Restart the service and confirm it registers**

Run:
```bash
systemctl --user restart voice-agent
sleep 8
journalctl --user -u voice-agent --no-pager -n 5 | grep -E "JIT warmup|models ready"
journalctl --user -u voice-livekit --no-pager -n 5 | grep "worker registered"
```
Expected: `models ready` from the agent and a `worker registered` line from the server.

- [ ] **Step 5: Live end-to-end test (MANUAL — human step)**

With an active Claude session in Happy and the phone on Tailscale:
1. Open the "Happy (preview)" app, enable voice.
2. Say a simple request, e.g. "Ask Claude to run git status and tell me what changed."
3. Confirm: the agent speaks a short summary, AND the full Claude reply appears in the Happy chat for that session.
4. Verify the target: `journalctl --user -u voice-agent -f` shows the send to the resolved session id.
5. Disable, then re-enable voice; confirm a fresh greeting and that a second request still works (reconnect fix).

Expected: spoken summary matches the chat reply's gist; no crash on disable/re-enable.

- [ ] **Step 6: Commit**

```bash
cd /home/hyggan/voice-agent
git add spike/agent.py
git commit -m "feat(voice): pipe voice turns to Claude via happy-agent bridge"
```

---

## Self-Review Notes

- **Spec coverage:** STT→happy-agent→summarize→TTS pipe (Tasks 2-5); no persistence in agent (delegated, Task 2); session target = newest active + `VOICE_SESSION_ID` override (Task 2/5); auth prereq + graceful failure (Tasks 1, 5); conservative summarizer + truncation fallback (Task 3); permission-block handling — see limitation below; reconnect fix preserved (Task 5).
- **Known limitation vs spec:** the spec's "detect a permission block and speak 'approve in the app'" is only partially covered. In v1, if Claude blocks on a permission request, `send --wait` returns when the turn ends and `fetch_last_reply` returns whatever the last agent message was (possibly empty → summarizer speaks the placeholder "check the chat for details"). Explicit permission-request detection (reading `agentState.requests`) and a tailored spoken notice is deferred; flagged for the executor to confirm behavior during Step 5 and raised as the first candidate for a follow-up task if the placeholder proves confusing.
- **Type consistency:** callable shapes match across Tasks 2/4/5 (`resolve_session_id(run, override)` is adapted at the call site — `HappyBridgeLLM` calls `resolve_session(override=...)`, and `agent.py` passes `happy_bridge.resolve_session_id` whose signature is `(run=_default_run, override=None)`, so the keyword `override=` binds correctly). `send_and_wait(session_id, text)` and `fetch_last_reply(session_id)` are called positionally with the default `run`.
