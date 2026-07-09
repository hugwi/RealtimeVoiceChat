"""Dispatch lifecycle for background Claude Code turns.

Owns concurrency: one in-flight turn per target session id, a per-session FIFO
queue, and parallelism across different sessions. It runs an injected async
`worker(payload)` (the actual Claude round-trip + spoken answer lives in
delivery.py). submit() never blocks the conversation."""
import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger("dispatcher")


@dataclass
class Payload:
    session_id: str
    instruction: str
    transcript: str
    user_request: str


def build_message(payload):
    """The text actually sent to Claude: distilled instruction + raw transcript.
    Nothing the user said is lost. Falls back to the raw user request if both
    instruction and transcript are empty."""
    parts = []
    if payload.instruction and payload.instruction.strip():
        parts.append(payload.instruction.strip())
    if payload.transcript and payload.transcript.strip():
        parts.append("Full transcript of what I said:\n" + payload.transcript.strip())
    return "\n\n".join(parts) or payload.user_request


class Dispatcher:
    def __init__(self):
        self._worker = None
        self._in_flight = set()
        self._queues = defaultdict(deque)

    def set_worker(self, worker):
        """worker: async def worker(payload) -> None."""
        self._worker = worker

    def in_flight(self, session_id):
        return session_id in self._in_flight

    def pending(self, session_id):
        return len(self._queues[session_id])

    def submit(self, payload):
        """Schedule a payload. Same session -> queue; else run now. Non-blocking.
        Must be called on the event loop (uses asyncio.create_task)."""
        sid = payload.session_id
        if sid in self._in_flight:
            self._queues[sid].append(payload)
            return
        self._in_flight.add(sid)
        asyncio.create_task(self._run(payload))

    async def _run(self, payload):
        sid = payload.session_id
        try:
            await self._worker(payload)
        except Exception:
            logger.exception("dispatch worker failed for session %s", sid)
        finally:
            self._in_flight.discard(sid)
            if self._queues[sid]:
                nxt = self._queues[sid].popleft()
                self._in_flight.add(sid)
                asyncio.create_task(self._run(nxt))
