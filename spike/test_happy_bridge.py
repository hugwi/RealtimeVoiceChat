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
