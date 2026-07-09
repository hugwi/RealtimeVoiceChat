"""Background answer delivery: the actual Claude Code round-trip for a dispatched
payload, run off the event loop, then spoken back. Wired into Dispatcher as its
worker. Never raises — always speaks something."""
import asyncio
import logging

import dispatcher
from happy_bridge import HappyAgentError

logger = logging.getLogger("delivery")

FALLBACK = "I couldn't reach that session. Check the chat."


def _tagged(spoken, payload, voice_state):
    """Prefix the spoken answer with the session's summary when it is NOT the
    focused session, so the user knows which background session replied."""
    if voice_state is None:
        return spoken
    if payload.session_id == getattr(voice_state, "focused_session_id", None):
        return spoken
    summary = voice_state.get_summary(payload.session_id)
    if summary:
        return f"From your {summary} session: {spoken}"
    return spoken


def make_deliver(*, send_and_wait, fetch_last_reply, summarize, say,
                 voice_state=None, run_blocking=None):
    async def _default_run_blocking(fn):
        return await asyncio.get_event_loop().run_in_executor(None, fn)

    run = run_blocking or _default_run_blocking

    async def deliver(payload):
        def blocking():
            send_and_wait(payload.session_id, dispatcher.build_message(payload))
            reply = fetch_last_reply(payload.session_id)
            return summarize(reply, payload.user_request)

        try:
            spoken = await run(blocking)
        except HappyAgentError as e:
            logger.warning("claude round-trip failed for %s: %s", payload.session_id, e)
            spoken = FALLBACK
        except Exception:
            logger.exception("delivery failed for %s", payload.session_id)
            spoken = FALLBACK
        await say(_tagged(spoken, payload, voice_state))

    return deliver
