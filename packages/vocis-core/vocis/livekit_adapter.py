from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from .gateway import HarnessClient, LiveKitVoiceGateway

logger = logging.getLogger(__name__)


def attach_livekit_gateway(room: Any, harness: HarnessClient) -> LiveKitVoiceGateway:
    """Attach the gateway to a LiveKit room without importing LiveKit types.

    The existing LiveKit worker passes its connected ``ctx.room`` here. Keeping
    the room structural makes this adapter testable and avoids coupling the
    protocol package to one LiveKit SDK release.
    """

    def publish(message: dict[str, object]) -> None:
        async def send() -> None:
            try:
                await room.local_participant.publish_data(
                    json.dumps(message),
                    reliable=True,
                    topic="voice.events.v1",
                )
            except Exception:
                logger.exception("failed to publish LiveKit voice event")

        asyncio.create_task(send())

    gateway = LiveKitVoiceGateway(harness, publish)

    def on_data_received(packet: Any) -> None:
        async def handle() -> None:
            try:
                await gateway.handle_data(packet.data)
            except Exception:
                logger.exception("failed to handle LiveKit voice command")

        asyncio.create_task(handle())

    room.on("data_received", on_data_received)
    return gateway


def attach_livekit_agent_session(
    agent_session: Any,
    gateway: LiveKitVoiceGateway,
    voice_session_id: str,
) -> None:
    """Route LiveKit Agents final STT events into the ACP gateway.

    Partial transcripts remain UI-only. Dispatching exclusively from final
    server-side transcripts avoids duplicating STT in the browser and keeps
    the irreversible coding request behind one endpointing decision.
    """

    def on_transcript(transcript_event: Any) -> None:
        if not getattr(transcript_event, "is_final", False):
            return
        text = str(getattr(transcript_event, "transcript", "")).strip()
        if not text:
            return
        turn_id = f"turn_{uuid.uuid4().hex}"
        asyncio.create_task(
            gateway.submit_final_turn(voice_session_id, turn_id, text)
        )

    agent_session.on("user_input_transcribed", on_transcript)
