import asyncio
from livekit.agents.llm import ChatContext
import happy_bridge as hb
import happy_llm


def _collect(llm, ctx):
    # The LLMStream base spawns a metrics task in __init__, so .chat() must be
    # called inside a running event loop.
    async def run():
        stream = llm.chat(chat_ctx=ctx)
        chunks = []
        async for chunk in stream:
            if chunk.delta and chunk.delta.content:
                chunks.append(chunk.delta.content)
        return "".join(chunks)
    return asyncio.run(run())


def _ctx(user_text):
    ctx = ChatContext.empty()
    ctx.add_message(role="user", content=user_text)
    return ctx


def test_happy_llm_speaks_summary_of_reply():
    calls = {}
    llm = happy_llm.HappyBridgeLLM(
        resolve_session=lambda override=None: "sid1",
        send_and_wait=lambda sid, text: calls.setdefault("sent", (sid, text)),
        fetch_last_reply=lambda sid: "Committed everything and opened PR 12.",
        summarize=lambda reply: "Committed and opened a PR.",
    )
    out = _collect(llm, _ctx("commit and open a PR"))
    assert calls["sent"] == ("sid1", "commit and open a PR")
    assert out == "Committed and opened a PR."


def test_happy_llm_speaks_error_on_happy_agent_failure():
    def boom(override=None):
        raise hb.HappyAgentError("no active Claude session found")
    llm = happy_llm.HappyBridgeLLM(
        resolve_session=boom,
        send_and_wait=lambda sid, text: None,
        fetch_last_reply=lambda sid: "",
        summarize=lambda reply: "unused",
    )
    out = _collect(llm, _ctx("do something"))
    assert "session" in out.lower()


def test_happy_llm_speaks_fallback_on_unexpected_error():
    # A non-HappyAgentError (e.g. malformed JSON from happy-agent) must still
    # produce spoken output, never silence.
    def boom(sid):
        raise ValueError("Expecting value: line 1 column 1")
    llm = happy_llm.HappyBridgeLLM(
        resolve_session=lambda override=None: "sid1",
        send_and_wait=lambda sid, text: None,
        fetch_last_reply=boom,
        summarize=lambda reply: "unused",
    )
    out = _collect(llm, _ctx("do something"))
    assert out.strip() != ""


def test_happy_llm_uses_session_override():
    seen = {}
    llm = happy_llm.HappyBridgeLLM(
        resolve_session=lambda override=None: seen.setdefault("override", override) or "resolved",
        send_and_wait=lambda sid, text: seen.setdefault("sid", sid),
        fetch_last_reply=lambda sid: "ok",
        summarize=lambda reply: "ok spoken",
        session_override="forced-sid",
    )
    _collect(llm, _ctx("hi"))
    assert seen["override"] == "forced-sid"
