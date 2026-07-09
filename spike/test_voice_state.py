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


def test_append_transcript_accumulates():
    s = vs.VoiceState()
    s.append_transcript("first")
    s.append_transcript("second")
    assert s.transcript_context() == "first\nsecond"


def test_append_transcript_skips_blank():
    s = vs.VoiceState()
    s.append_transcript("  ")
    s.append_transcript("")
    assert s.transcript_context() == ""


def test_append_transcript_bounds_to_max_turns():
    s = vs.VoiceState()
    for i in range(25):
        s.append_transcript(f"line{i}", max_turns=20)
    lines = s.transcript_context().split("\n")
    assert len(lines) == 20
    assert lines[0] == "line5"
    assert lines[-1] == "line24"


def test_drain_transcript_returns_and_clears():
    s = vs.VoiceState()
    s.append_transcript("a")
    s.append_transcript("b")
    assert s.drain_transcript() == "a\nb"
    assert s.transcript_context() == ""