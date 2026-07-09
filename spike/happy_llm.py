"""Conversational front-end for the two-tier voice bridge.

Per user turn: append the turn to the transcript buffer, classify it, then
either speak a live conversational reply (chit-chat) or hand a payload to the
Dispatcher and speak a brief ack (actionable task). The blocking Claude Code
round-trip lives entirely in the background (delivery.py), so the conversation
never freezes."""
import asyncio
import logging
import uuid

from livekit.agents.llm import LLM, LLMStream, ChatChunk, ChoiceDelta
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

import classifier
import dispatcher as dispatcher_mod
from happy_bridge import HappyAgentError

logger = logging.getLogger("happy_llm")

ACK = "On it. I'll let you know when it's done."
_CHITCHAT_FALLBACK = "Okay."


def _last_user_text(chat_ctx):
    for item in reversed(chat_ctx.items):
        if getattr(item, "role", None) != "user":
            continue
        content = getattr(item, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [p for p in content if isinstance(p, str)]
            if parts:
                return " ".join(parts).strip()
    return ""


class HappyBridgeLLM(LLM):
    def __init__(self, *, converse, classify, dispatcher, resolve_session,
                 session_override=None, voice_state=None):
        super().__init__()
        self._converse = converse
        self._classify = classify
        self._dispatcher = dispatcher
        self._resolve_session = resolve_session
        self._session_override = session_override
        self._voice_state = voice_state

    def chat(self, *, chat_ctx, tools=None,
             conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        user_text = _last_user_text(chat_ctx)
        return _FrontEndStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            user_text=user_text,
        )


class _FrontEndStream(LLMStream):
    def __init__(self, llm, *, chat_ctx, tools, conn_options, user_text):
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._llm_impl = llm
        self._user_text = user_text

    def _emit(self, spoken):
        self._event_ch.send_nowait(
            ChatChunk(
                id=str(uuid.uuid4()),
                delta=ChoiceDelta(role="assistant", content=spoken),
            )
        )

    async def _run(self):
        impl = self._llm_impl
        vs = impl._voice_state
        user_text = self._user_text
        loop = asyncio.get_event_loop()

        if vs is not None:
            vs.append_transcript(user_text)
        context = vs.transcript_context() if vs is not None else ""

        try:
            cls = await loop.run_in_executor(
                None, lambda: impl._classify(user_text, context)
            )
        except Exception:
            logger.warning("classify failed; degrading to raw-transcript task")
            cls = classifier.Classification(is_task=True, instruction="")

        try:
            if cls.is_task:
                spoken = await self._dispatch_task(impl, vs, cls, user_text, loop)
            else:
                spoken = await self._chitchat(impl, context, user_text, loop)
        except HappyAgentError as e:
            spoken = f"Sorry, I couldn't reach the coding session: {e}."
        except Exception:
            logger.exception("front-end turn failed")
            spoken = ACK

        self._emit(spoken)

    async def _dispatch_task(self, impl, vs, cls, user_text, loop):
        instruction = cls.instruction or user_text
        transcript = vs.drain_transcript() if vs is not None else user_text
        focused = getattr(vs, "focused_session_id", None) if vs is not None else None
        session_id = await loop.run_in_executor(
            None,
            lambda: impl._resolve_session(
                override=impl._session_override, focused=focused
            ),
        )
        payload = dispatcher_mod.Payload(
            session_id=session_id,
            instruction=instruction,
            transcript=transcript,
            user_request=user_text,
        )
        impl._dispatcher.submit(payload)
        return ACK

    async def _chitchat(self, impl, context, user_text, loop):
        reply = await loop.run_in_executor(
            None, lambda: impl._converse(user_text, context)
        )
        return reply or _CHITCHAT_FALLBACK
