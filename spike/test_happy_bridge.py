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


# --- Real happy-agent history shape ---
# Assistant text lives at content.content.ev = {"t": "text", "text": ...},
# grouped by content.content.turn. thinking events and tool-call events
# (ev.t != "text") carry no spoken text. User messages have no ev.

def _agent_text(turn, text, thinking=False):
    ev = {"t": "text", "text": text}
    if thinking:
        ev["thinking"] = True
    return {"content": {"role": "session",
                        "content": {"role": "agent", "turn": turn, "ev": ev}}}


def _agent_tool(turn):
    return {"content": {"role": "session",
                        "content": {"role": "agent", "turn": turn,
                                    "ev": {"t": "tool-call-start", "call": "x", "name": "Bash"}}}}


def _user_msg(text):
    return {"content": {"role": "user", "content": {"type": "text", "text": text}}}


def test_fetch_last_reply_extracts_agent_text():
    messages = [_user_msg("commit and push"), _agent_text("t1", "Committed and opened PR #12.")]
    def run(args):
        assert args[0] == "history"
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == "Committed and opened PR #12."


def test_fetch_last_reply_concatenates_text_of_last_turn():
    messages = [
        _agent_text("t1", "Old turn text."),
        _agent_text("t2", "First part."),
        _agent_tool("t2"),
        _agent_text("t2", "Second part."),
    ]
    def run(args):
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == "First part. Second part."


def test_fetch_last_reply_skips_thinking_and_tool_events():
    messages = [
        _agent_text("t3", "", thinking=True),
        _agent_tool("t3"),
        _agent_text("t3", "Done deploying."),
    ]
    def run(args):
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == "Done deploying."


def test_fetch_last_reply_ignores_user_messages():
    messages = [_agent_text("t1", "All set."), _user_msg("thanks")]
    def run(args):
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == "All set."


def test_fetch_last_reply_empty_when_no_agent_text():
    messages = [_user_msg("hi"), _agent_tool("t1"), _agent_text("t1", "", thinking=True)]
    def run(args):
        return json.dumps(messages)
    assert hb.fetch_last_reply("sid1", run=run) == ""
