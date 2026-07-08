"""Thin wrappers around the happy-agent CLI. No persistence lives here —
happy-agent (and Happy) own sessions, encryption, and history."""
import json
import os
import subprocess

HAPPY_AGENT_BIN = os.environ.get(
    "HAPPY_AGENT_BIN", "/home/hyggan/voice-agent/bin/happy-agent"
)
AGENT_KEY_PATH = os.path.expanduser("~/.happy/agent.key")
# Scan enough recent messages to cover a full agent turn (text interleaved with
# many tool calls). A turn can span dozens of events.
_HISTORY_SCAN = 60


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


def resolve_session_id(run=_default_run, override=None, focused=None):
    """Return the target session id. Priority: override → focused →
    most-recently-active session (max activeAt)."""
    if override:
        return override
    if focused:
        return focused
    sessions = json.loads(run(["list", "--active", "--json"]))
    if not sessions:
        raise HappyAgentError("no active Claude session found")
    sessions.sort(
        key=lambda s: s.get("activeAt") or s.get("updatedAt") or 0,
        reverse=True,
    )
    return sessions[0]["id"]


def active_sessions_with_summary(run=_default_run):
    """Return [{id, summary, activeAt}] for active sessions, newest-active
    first. summary is metadata.summary.text or ''. activeAt is the session's
    activeAt (or updatedAt fallback, or 0). Seeds/refreshes voice_state."""
    sessions = json.loads(run(["list", "--active", "--json"]))
    out = []
    for s in sessions:
        meta = s.get("metadata") or {}
        summary = (meta.get("summary") or {}).get("text") or ""
        out.append({
            "id": s["id"],
            "summary": summary,
            "activeAt": s.get("activeAt") or s.get("updatedAt") or 0,
        })
    out.sort(key=lambda x: x["activeAt"], reverse=True)
    return out


def send_and_wait(session_id, text, run=_default_run):
    """Send a message to the session and block until the agent turn completes."""
    run(["send", session_id, text, "--wait"])


def _agent_text_event(message):
    """If a history message is an agent spoken-text event, return
    (turn, text); otherwise None. Skips user messages (no ev), thinking
    events, and tool-call events (ev.t != 'text')."""
    content = message.get("content")
    if not isinstance(content, dict):
        return None
    inner = content.get("content")
    if not isinstance(inner, dict):
        return None
    ev = inner.get("ev")
    if not isinstance(ev, dict) or ev.get("t") != "text" or ev.get("thinking"):
        return None
    text = (ev.get("text") or "").strip()
    if not text:
        return None
    return inner.get("turn"), text


def fetch_last_reply(session_id, run=_default_run):
    """Return the agent's most recent spoken reply — all text events of the
    latest turn, concatenated in order — or '' if there is none."""
    messages = json.loads(
        run(["history", session_id, "--limit", str(_HISTORY_SCAN), "--json"])
    )
    events = [e for e in (_agent_text_event(m) for m in messages) if e]
    if not events:
        return ""
    last_turn = events[-1][0]
    if last_turn is None:
        return events[-1][1]
    return " ".join(text for turn, text in events if turn == last_turn).strip()
