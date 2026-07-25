from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from .omnigent_backend import BackendEvent, OmnigentBackend

Notify = Callable[[dict[str, Any]], Awaitable[None]]
RequestPermission = Callable[[dict[str, Any]], Awaitable[str]]


class OmnigentAcpAgent:
    """ACP v1 agent that exposes existing OmniGent sessions."""

    def __init__(self, backend: OmnigentBackend) -> None:
        self._backend = backend
        self._sessions: dict[str, str] = {}

    async def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion", 1)
        return {
            "protocolVersion": 1 if requested != 1 else requested,
            "agentInfo": {"name": "omnigent-acp-voice-bridge", "version": "0.1.0"},
            "agentCapabilities": {"loadSession": True},
        }

    async def load_session(
        self, acp_session_id: str, omnigent_session_id: str
    ) -> dict[str, Any]:
        await self._backend.require_session(omnigent_session_id)
        self._sessions[acp_session_id] = omnigent_session_id
        return {"sessionId": acp_session_id}

    async def new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        meta = params.get("_meta")
        target = meta.get("omnigentSessionId") if isinstance(meta, dict) else None
        if not isinstance(target, str) or not target:
            raise ValueError(
                "session/new requires _meta.omnigentSessionId in this attach-only prototype"
            )
        acp_session_id = f"acp_{uuid.uuid4().hex}"
        return await self.load_session(acp_session_id, target)

    async def prompt(
        self,
        params: dict[str, Any],
        notify: Notify,
        request_permission: RequestPermission,
    ) -> dict[str, Any]:
        acp_session_id = _required_string(params, "sessionId")
        target = self._target(acp_session_id)
        text = _prompt_text(params.get("prompt"))
        stop_reason = "end_turn"
        async for event in self._backend.send(target, text):
            await self._forward_event(
                acp_session_id, target, event, notify, request_permission
            )
            if event.kind == "cancelled":
                stop_reason = "cancelled"
            elif event.kind == "failed":
                raise RuntimeError(event.text or "OmniGent request failed")
        return {"stopReason": stop_reason}

    async def cancel(self, acp_session_id: str) -> None:
        await self._backend.cancel(self._target(acp_session_id))

    def _target(self, acp_session_id: str) -> str:
        try:
            return self._sessions[acp_session_id]
        except KeyError as exc:
            raise LookupError(f"unknown ACP session: {acp_session_id}") from exc

    async def _forward_event(
        self,
        acp_session_id: str,
        target: str,
        event: BackendEvent,
        notify: Notify,
        request_permission: RequestPermission,
    ) -> None:
        if event.kind == "text_delta":
            await notify(
                {
                    "sessionId": acp_session_id,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": event.text},
                    },
                }
            )
        elif event.kind == "permission":
            decision = await request_permission(
                {
                    "sessionId": acp_session_id,
                    "toolCall": {
                        "toolCallId": event.request_id,
                        "title": event.title,
                        "kind": "other",
                        "status": "pending",
                    },
                    "options": [
                        {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "deny", "name": "Deny", "kind": "reject_once"},
                    ],
                }
            )
            permission_target = event.target_session_id or target
            await self._backend.resolve_permission(
                permission_target, event.request_id, decision
            )


class InProcessAcpClient:
    """Small ACP client used by the tracer and contract tests."""

    def __init__(self, agent: OmnigentAcpAgent) -> None:
        self._agent = agent
        self._permission_handler: Callable[[dict[str, Any]], Awaitable[str]] | None = None

    async def initialize(self) -> dict[str, Any]:
        return await self._agent.initialize(
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "voice-runtime", "version": "0.1.0"},
                "clientCapabilities": {},
            }
        )

    async def load_session(self, acp_session_id: str, target_id: str) -> None:
        await self._agent.load_session(acp_session_id, target_id)

    def set_permission_handler(
        self, handler: Callable[[dict[str, Any]], Awaitable[str]]
    ) -> None:
        self._permission_handler = handler

    async def prompt(
        self, session_id: str, text: str
    ) -> AsyncIterator[BackendEvent]:
        notifications: list[dict[str, Any]] = []

        async def notify(params: dict[str, Any]) -> None:
            notifications.append(params)

        async def request_permission(params: dict[str, Any]) -> str:
            if self._permission_handler is None:
                raise RuntimeError("no ACP permission handler registered")
            return await self._permission_handler(params)

        result = await self._agent.prompt(
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": text}],
            },
            notify,
            request_permission,
        )
        for params in notifications:
            update = params.get("update", {})
            if update.get("sessionUpdate") == "agent_message_chunk":
                content = update.get("content", {})
                yield BackendEvent(kind="text_delta", text=str(content.get("text", "")))
        stop_reason = result.get("stopReason")
        yield BackendEvent(
            kind=(
                "completed"
                if stop_reason == "end_turn"
                else "cancelled"
                if stop_reason == "cancelled"
                else "failed"
            )
        )

    async def cancel(self, session_id: str) -> None:
        await self._agent.cancel(session_id)


def _required_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _prompt_text(raw: Any) -> str:
    if not isinstance(raw, list):
        raise ValueError("prompt must be a list")
    parts = [
        block.get("text", "")
        for block in raw
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    text = "\n".join(part for part in parts if isinstance(part, str)).strip()
    if not text:
        raise ValueError("prompt must contain non-empty text")
    return text
