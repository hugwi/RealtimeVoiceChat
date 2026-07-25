from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendEvent:
    kind: str
    text: str = ""
    request_id: str = ""
    title: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    success: bool | None = None
    target_session_id: str = ""


class OmnigentBackend(Protocol):
    async def require_session(self, session_id: str) -> None: ...

    def send(self, session_id: str, text: str) -> AsyncIterator[BackendEvent]: ...

    async def cancel(self, session_id: str) -> None: ...

    async def resolve_permission(
        self, session_id: str, request_id: str, decision: str
    ) -> None: ...


class OmnigentSdkBackend:
    """Adapter over OmniGent's supported ``omnigent_client`` interface.

    This module imports the SDK lazily so protocol tests can run under the
    voice-agent Python 3.11 environment while the real bridge runs with
    OmniGent's Python 3.12 tool environment.
    """

    def __init__(self, base_url: str, *, auth: Any = None) -> None:
        try:
            from omnigent_client import OmnigentClient
        except ImportError as exc:  # pragma: no cover - operator setup path
            raise RuntimeError(
                "omnigent_client is unavailable; run the bridge with OmniGent's Python"
            ) from exc
        token = os.environ.get("OMNIGENT_AUTH_TOKEN", "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        self._client = OmnigentClient(base_url=base_url, headers=headers, auth=auth)

    async def require_session(self, session_id: str) -> None:
        await self._client.sessions.get(session_id)

    async def send(self, session_id: str, text: str) -> AsyncIterator[BackendEvent]:
        # OmniGent's session SSE contract has no replay. Start the stream and
        # wait for its ready heartbeat before posting the input, otherwise fast
        # deltas can be lost between POST and GET /stream.
        queue: asyncio.Queue[Any] = asyncio.Queue()
        ready = asyncio.Event()

        async def pump() -> None:
            try:
                async for event in self._client.sessions.stream(session_id):
                    event_type = getattr(event, "type", "")
                    if event_type == "session.heartbeat":
                        ready.set()
                        continue
                    await queue.put(event)
            except BaseException as exc:
                await queue.put(exc)
            finally:
                await queue.put(None)

        stream_task = asyncio.create_task(pump())
        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
            await self._client.sessions.post_event(
                session_id,
                {
                    "type": "message",
                    "data": {
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    },
                },
            )
            while True:
                event = await queue.get()
                if event is None:
                    break
                if isinstance(event, BaseException):
                    raise event
                translated = _translate_sdk_event(event)
                if translated is None:
                    continue
                yield translated
                if translated.kind in {"completed", "failed", "cancelled"}:
                    break
        finally:
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)

    async def cancel(self, session_id: str) -> None:
        await self._client.sessions.interrupt(session_id)

    async def resolve_permission(
        self, session_id: str, request_id: str, decision: str
    ) -> None:
        action = {"allow": "accept", "deny": "decline", "cancel": "cancel"}.get(
            decision
        )
        if action is None:
            raise ValueError(f"unsupported permission decision: {decision}")
        await self._client.sessions.resolve_elicitation(
            session_id, request_id, {"action": action}
        )

    async def close(self) -> None:
        await self._client.close()


def _translate_sdk_event(event: Any) -> BackendEvent | None:
    event_type = getattr(event, "type", "")

    if event_type == "response.output_text.delta":
        return BackendEvent(kind="text_delta", text=str(getattr(event, "delta", "")))
    if event_type == "response.elicitation_request":
        params = getattr(event, "params", None)
        return BackendEvent(
            kind="permission",
            request_id=str(getattr(event, "elicitation_id", "")),
            title=str(getattr(params, "message", "Permission requested")),
            target_session_id=str(
                getattr(params, "target_session_id", "") or ""
            ),
        )
    # Native harnesses can emit response.completed before their forwarded text
    # deltas. The session's idle edge is the authoritative end of the turn.
    if event_type == "response.completed":
        return None
    if event_type == "session.status":
        status = str(getattr(event, "status", ""))
        if status == "idle":
            return BackendEvent(kind="completed")
        if status == "error":
            error = getattr(event, "error", None)
            return BackendEvent(kind="failed", text=str(error or "Agent failed"))
        return None
    if event_type == "turn.completed":
        return BackendEvent(kind="completed")
    if event_type in {"response.cancelled", "session.interrupted", "turn.cancelled"}:
        return BackendEvent(kind="cancelled")
    if event_type in {"response.failed", "response.error", "turn.failed"}:
        error = getattr(event, "error", None)
        return BackendEvent(
            kind="failed", text=str(getattr(error, "message", "Agent failed"))
        )
    return None
