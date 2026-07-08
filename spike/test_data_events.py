import json
import data_events as de


def _enc(obj):
    return json.dumps(obj).encode()


def test_valid_focused_session():
    ev = de.parse(_enc({"type": "focused_session", "sessionId": "A"}))
    assert isinstance(ev, de.FocusEvent)
    assert ev.session_id == "A"


def test_valid_session_complete():
    ev = de.parse(_enc({"type": "session_complete", "sessionId": "B"}))
    assert isinstance(ev, de.CompleteEvent)
    assert ev.session_id == "B"


def test_bad_json_returns_none():
    assert de.parse(b"not json") is None
    assert de.parse(b"{") is None


def test_unknown_type_returns_none():
    assert de.parse(_enc({"type": "mystery", "sessionId": "A"})) is None


def test_missing_session_id_returns_none():
    assert de.parse(_enc({"type": "focused_session"})) is None


def test_empty_session_id_returns_none():
    assert de.parse(_enc({"type": "focused_session", "sessionId": ""})) is None


def test_wrong_type_session_id_returns_none():
    assert de.parse(_enc({"type": "focused_session", "sessionId": 123})) is None


def test_non_dict_json_returns_none():
    assert de.parse(_enc([1, 2, 3])) is None
    assert de.parse(_enc("a string")) is None


def test_accepts_bytes_input():
    ev = de.parse(_enc({"type": "session_complete", "sessionId": "C"}))
    assert isinstance(ev, de.CompleteEvent)
    assert ev.session_id == "C"