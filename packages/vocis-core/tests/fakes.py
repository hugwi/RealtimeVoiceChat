from __future__ import annotations

from collections.abc import AsyncIterator

from vocis.omnigent_backend import BackendEvent


class FakeOmnigentBackend:
    def __init__(self, events: list[BackendEvent] | None = None) -> None:
        self.events = events or []
        self.sent: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self.resolved: list[tuple[str, str, str]] = []

    async def require_session(self, session_id: str) -> None:
        if not session_id.startswith("conv_"):
            raise LookupError(session_id)

    async def send(self, session_id: str, text: str) -> AsyncIterator[BackendEvent]:
        self.sent.append((session_id, text))
        for event in self.events:
            yield event

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)

    async def resolve_permission(
        self, session_id: str, request_id: str, decision: str
    ) -> None:
        self.resolved.append((session_id, request_id, decision))
