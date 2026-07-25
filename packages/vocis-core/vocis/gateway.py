from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from .livekit_protocol import (
    CancelTurn,
    FinalTurn,
    PermissionResponse,
    event,
    parse_client_message,
)
from .omnigent_backend import BackendEvent


class HarnessClient(Protocol):
    def prompt(self, session_id: str, text: str) -> AsyncIterator[BackendEvent]: ...

    async def cancel(self, session_id: str) -> None: ...

    def set_permission_handler(
        self, handler: Callable[[dict[str, Any]], Awaitable[str]]
    ) -> None: ...


class LiveKitVoiceGateway:
    """Translate versioned LiveKit data messages to a harness session."""

    def __init__(
        self,
        harness: HarnessClient,
        publish: Callable[[dict[str, object]], None],
    ) -> None:
        self._harness = harness
        self._publish = publish
        self._active_turns: dict[str, str] = {}
        self._permissions: dict[str, tuple[str, str, asyncio.Future[str]]] = {}
        harness.set_permission_handler(self._request_permission)

    async def handle_data(self, raw: bytes) -> None:
        message = parse_client_message(raw)
        if message is None:
            return
        if isinstance(message, PermissionResponse):
            self._resolve_permission(message)
            return
        if isinstance(message, CancelTurn):
            await self._harness.cancel(message.voice_session_id)
            self._publish(
                event(
                    "harness.cancelled",
                    message.voice_session_id,
                    message.turn_id,
                )
            )
            return
        await self._dispatch(message)

    async def submit_final_turn(
        self, voice_session_id: str, turn_id: str, text: str
    ) -> None:
        """Submit a server-side final STT result from LiveKit Agents."""
        normalized = text.strip()
        if not normalized:
            return
        await self._dispatch(FinalTurn(voice_session_id, turn_id, normalized))

    async def _dispatch(self, turn: FinalTurn) -> None:
        self._active_turns[turn.voice_session_id] = turn.turn_id
        self._publish(
            event("voice.turn.accepted", turn.voice_session_id, turn.turn_id)
        )
        full_text = ""
        try:
            async for update in self._harness.prompt(turn.voice_session_id, turn.text):
                if update.kind == "text_delta":
                    full_text += update.text
                    self._publish(
                        event(
                            "harness.text.delta",
                            turn.voice_session_id,
                            turn.turn_id,
                            text=update.text,
                        )
                    )
                elif update.kind == "completed":
                    self._publish(
                        event(
                            "harness.completed",
                            turn.voice_session_id,
                            turn.turn_id,
                            text=full_text,
                        )
                    )
                elif update.kind == "failed":
                    self._publish(
                        event(
                            "harness.failed",
                            turn.voice_session_id,
                            turn.turn_id,
                            message=update.text or "Harness failed",
                        )
                    )
                elif update.kind == "cancelled":
                    self._publish(
                        event(
                            "harness.cancelled",
                            turn.voice_session_id,
                            turn.turn_id,
                        )
                    )
        except Exception as exc:
            self._publish(
                event(
                    "harness.failed",
                    turn.voice_session_id,
                    turn.turn_id,
                    message=str(exc) or "Harness failed",
                )
            )
        finally:
            if self._active_turns.get(turn.voice_session_id) == turn.turn_id:
                self._active_turns.pop(turn.voice_session_id, None)

    async def _request_permission(self, params: dict[str, Any]) -> str:
        voice_session_id = str(params.get("sessionId", ""))
        turn_id = self._active_turns.get(voice_session_id, "")
        tool_call = params.get("toolCall")
        if not isinstance(tool_call, dict):
            raise ValueError("ACP permission request is missing toolCall")
        request_id = str(tool_call.get("toolCallId", ""))
        if not request_id or not turn_id:
            raise ValueError("ACP permission request is not correlated to an active turn")
        if request_id in self._permissions:
            raise ValueError(f"duplicate permission request: {request_id}")
        future = asyncio.get_running_loop().create_future()
        self._permissions[request_id] = (voice_session_id, turn_id, future)
        self._publish(
            event(
                "harness.permission.requested",
                voice_session_id,
                turn_id,
                requestId=request_id,
                title=str(tool_call.get("title", "Permission requested")),
                options=params.get("options", []),
            )
        )
        try:
            return await future
        finally:
            self._permissions.pop(request_id, None)

    def _resolve_permission(self, response: PermissionResponse) -> None:
        pending = self._permissions.get(response.request_id)
        if pending is None:
            return
        voice_session_id, turn_id, future = pending
        if (
            voice_session_id != response.voice_session_id
            or turn_id != response.turn_id
            or future.done()
        ):
            return
        future.set_result(response.decision)
