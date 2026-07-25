from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from .omnigent_backend import BackendEvent


class _VoiceAcpCallbacks:
    def __init__(self) -> None:
        self.owner: OfficialSdkAcpHarnessClient | None = None

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        if self.owner is not None:
            await self.owner.receive_update(session_id, update)

    async def request_permission(
        self, session_id: str, tool_call: Any, options: list[Any], **kwargs: Any
    ) -> Any:
        from acp.schema import AllowedOutcome, DeniedOutcome, RequestPermissionResponse

        if self.owner is None:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        decision = await self.owner.request_permission(session_id, tool_call, options)
        if decision == "cancel":
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", option_id=decision)
        )

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        from acp import RequestError

        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None


class OfficialSdkAcpHarnessClient:
    """Harness interface backed by an official ACP client connection."""

    def __init__(self, connection: Any, callbacks: _VoiceAcpCallbacks) -> None:
        self._connection = connection
        self._callbacks = callbacks
        self._callbacks.owner = self
        self._queues: dict[str, asyncio.Queue[BackendEvent]] = {}
        self._permission_handler: Callable[[dict[str, Any]], Awaitable[str]] | None = None

    def set_permission_handler(
        self, handler: Callable[[dict[str, Any]], Awaitable[str]]
    ) -> None:
        self._permission_handler = handler

    async def prompt(self, session_id: str, text: str) -> AsyncIterator[BackendEvent]:
        from acp import text_block

        if session_id in self._queues:
            raise RuntimeError(f"ACP session already has an active prompt: {session_id}")
        queue: asyncio.Queue[BackendEvent] = asyncio.Queue()
        self._queues[session_id] = queue
        prompt_task = asyncio.create_task(
            self._connection.prompt(session_id=session_id, prompt=[text_block(text)])
        )
        try:
            while True:
                if prompt_task.done() and queue.empty():
                    result = await prompt_task
                    yield BackendEvent(
                        kind=(
                            "cancelled"
                            if result.stop_reason == "cancelled"
                            else "completed"
                            if result.stop_reason == "end_turn"
                            else "failed"
                        )
                    )
                    break
                event_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {event_task, prompt_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if event_task in done:
                    yield event_task.result()
                else:
                    event_task.cancel()
                    await asyncio.gather(event_task, return_exceptions=True)
        finally:
            self._queues.pop(session_id, None)

    async def cancel(self, session_id: str) -> None:
        await self._connection.cancel(session_id=session_id)

    async def receive_update(self, session_id: str, update: Any) -> None:
        queue = self._queues.get(session_id)
        if queue is None:
            return
        if getattr(update, "session_update", "") == "agent_message_chunk":
            content = getattr(update, "content", None)
            text = getattr(content, "text", "")
            if text:
                await queue.put(BackendEvent(kind="text_delta", text=text))

    async def request_permission(
        self, session_id: str, tool_call: Any, options: list[Any]
    ) -> str:
        if self._permission_handler is None:
            return "cancel"
        return await self._permission_handler(
            {
                "sessionId": session_id,
                "toolCall": {
                    "toolCallId": tool_call.tool_call_id,
                    "title": tool_call.title or "Permission requested",
                    "kind": tool_call.kind or "other",
                    "status": tool_call.status or "pending",
                },
                "options": [option.model_dump(by_alias=True) for option in options],
            }
        )


@asynccontextmanager
async def spawn_omnigent_acp_harness(
    command: str,
    args: Sequence[str],
    *,
    session_id: str,
    cwd: str | None = None,
) -> AsyncIterator[OfficialSdkAcpHarnessClient]:
    """Spawn the ACP bridge and attach it to an existing OmniGent session."""

    from acp import PROTOCOL_VERSION
    from acp.schema import ClientCapabilities, Implementation
    from acp.stdio import spawn_agent_process

    callbacks = _VoiceAcpCallbacks()
    async with spawn_agent_process(callbacks, command, *args, cwd=cwd) as (
        connection,
        _process,
    ):
        await connection.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(
                name="livekit-voice-runtime",
                title="LiveKit Voice Runtime",
                version="0.1.0",
            ),
        )
        await connection.load_session(
            cwd=cwd or os.getcwd(), session_id=session_id, mcp_servers=[]
        )
        yield OfficialSdkAcpHarnessClient(connection, callbacks)
