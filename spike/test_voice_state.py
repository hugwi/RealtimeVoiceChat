import voice_state as vs


def test_set_focus_updates_id():
    s = vs.VoiceState()
    assert s.focused_session_id is None
    s.set_focus("A")
    assert s.focused_session_id == "A"


def test_set_focus_last_write_wins():
    s = vs.VoiceState()
    s.set_focus("A")
    s.set_focus("B")
    assert s.focused_session_id == "B"


def test_summary_cache_roundtrip():
    s = vs.VoiceState()
    assert s.get_summary("A") is None
    s.set_summary("A", "Fix the bug.")
    assert s.get_summary("A") == "Fix the bug."


def test_set_summary_none_is_noop():
    s = vs.VoiceState()
    s.set_summary(None, "should not store")
    assert s.summary_cache == {}


def test_set_summary_overwrites():
    s = vs.VoiceState()
    s.set_summary("A", "one")
    s.set_summary("A", "two")
    assert s.get_summary("A") == "two"