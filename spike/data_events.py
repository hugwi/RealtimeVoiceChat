"""Isolated parser for structured LiveKit data-channel messages.

The ONLY place that knows the wire format between the Happy app and the voice
bridge. parse() never raises — bad/unknown/missing-field payloads yield None.
"""
import json
from dataclasses import dataclass


@dataclass
class FocusEvent:
    session_id: str


@dataclass
class CompleteEvent:
    session_id: str


def parse(raw: bytes) -> FocusEvent | CompleteEvent | None:
    """Decode a data-channel payload into an Event, or None on any malformed
    input. Never raises."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    t = payload.get("type")
    sid = payload.get("sessionId")
    if not isinstance(sid, str) or not sid:
        return None
    if t == "focused_session":
        return FocusEvent(session_id=sid)
    if t == "session_complete":
        return CompleteEvent(session_id=sid)
    return None