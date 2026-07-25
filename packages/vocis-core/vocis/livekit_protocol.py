from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FinalTurn:
    voice_session_id: str
    turn_id: str
    text: str


@dataclass(frozen=True)
class CancelTurn:
    voice_session_id: str
    turn_id: str


@dataclass(frozen=True)
class PermissionResponse:
    voice_session_id: str
    turn_id: str
    request_id: str
    decision: str


def parse_client_message(
    raw: bytes,
) -> FinalTurn | CancelTurn | PermissionResponse | None:
    try:
        message = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(message, dict) or message.get("v") != 1:
        return None
    voice_session_id = _string(message, "voiceSessionId")
    turn_id = _string(message, "turnId")
    if not voice_session_id or not turn_id:
        return None
    if message.get("type") == "voice.turn.final":
        text = _string(message, "text")
        return FinalTurn(voice_session_id, turn_id, text) if text else None
    if message.get("type") == "voice.turn.cancel":
        return CancelTurn(voice_session_id, turn_id)
    if message.get("type") == "harness.permission.respond":
        request_id = _string(message, "requestId")
        decision = _string(message, "decision")
        if request_id and decision in {"allow", "deny", "cancel"}:
            return PermissionResponse(
                voice_session_id, turn_id, request_id, decision
            )
    return None


def event(
    message_type: str,
    voice_session_id: str,
    turn_id: str,
    **fields: Any,
) -> dict[str, object]:
    return {
        "v": 1,
        "type": message_type,
        "voiceSessionId": voice_session_id,
        "turnId": turn_id,
        **fields,
    }


def _string(message: dict[str, Any], key: str) -> str:
    value = message.get(key)
    return value.strip() if isinstance(value, str) else ""
