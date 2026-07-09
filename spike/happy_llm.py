"""A LiveKit LLM whose 'completion' is: forward the user's turn to a Claude
Code session via happy-agent, then speak a summary of Claude's reply."""
import asyncio
import logging
import uuid

from livekit.agents.llm import LLM, LLMStream, ChatChunk, ChoiceDelta
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from happy_bridge import HappyAgentError

logger = logging.getLogger("happy_llm")


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
    def __init__(self, *, resolve_session, send_and_wait, fetch_last_reply,
                 summarize, session_override=None, voice_state=None):
        super().__init__()
        self._resolve_session = resolve_session
        self._send_and_wait = send_and_wait
        self._fetch_last_reply = fetch_last_reply
        self._summarize = summarize
        self._session_override = session_override
        self._voice_state = voice_state

    def chat(self, *, chat_ctx, tools=None,
             conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        user_text = _last_user_text(chat_ctx)
        return _HappyStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            user_text=user_text,
        )


class _HappyStream(LLMStream):
    def __init__(self, llm, *, chat_ctx, tools, conn_options, user_text):
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._llm_impl = llm
        self._user_text = user_text
    def _blocking_bridge(self):
        impl = self._llm_impl
        focused = (impl._voice_state.focused_session_id
                   if impl._voice_state else None)
        session_id = impl._resolve_session(
            override=impl._session_override, focused=focused,
        )
        impl._send_and_wait(session_id, self._user_text)
        reply = impl._fetch_last_reply(session_id)
        # Pass the user's request so the summary adapts to it: concise by default,
        # deeper when the user asked to "dive into the code", "explain", etc.
        return impl._summarize(reply, self._user_text)


    async def _run(self):
        try:
            spoken = await asyncio.get_event_loop().run_in_executor(
                None, self._blocking_bridge
            )
        except HappyAgentError as e:
            spoken = f"Sorry, I couldn't reach the coding session: {e}."
        except Exception as e:
            # Any other failure (e.g. malformed happy-agent output) must still
            # speak something — never leave the user with silence.
            logger.exception("happy bridge turn failed")
            spoken = "Sorry, something went wrong talking to the coding session. Check the chat."
        self._event_ch.send_nowait(
            ChatChunk(
                id=str(uuid.uuid4()),
                delta=ChoiceDelta(role="assistant", content=spoken),
            )
        )
