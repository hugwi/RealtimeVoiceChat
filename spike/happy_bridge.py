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
