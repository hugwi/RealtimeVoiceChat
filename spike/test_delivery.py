import asyncio
import delivery
from dispatcher import Payload
from happy_bridge import HappyAgentError


async def _passthrough(fn):
    return fn()


def _run(deliver, payload):
    asyncio.run(deliver(payload))


def test_deliver_sends_summarizes_and_says():
    sent = []
    said = []
    deliver = delivery.make_deliver(
        send_and_wait=lambda sid, text: sent.append((sid, text)),
        fetch_last_reply=lambda sid: "raw claude reply",
        summarize=lambda reply, req: f"summary of {reply} for {req}",
        say=lambda text: said.append(text) or asyncio.sleep(0),
        run_blocking=_passthrough,
    )
    _run(deliver, Payload("sid1", "commit the code", "commit the code please", "commit"))
    assert sent[0][0] == "sid1"
    assert "commit the code" in sent[0][1]
    assert "commit the code please" in sent[0][1]
    assert said == ["summary of raw claude reply for commit"]


def test_deliver_speaks_fallback_on_happy_agent_error():
    said = []

    def boom(sid, text):
        raise HappyAgentError("session gone")

    deliver = delivery.make_deliver(
        send_and_wait=boom,
        fetch_last_reply=lambda sid: "",
        summarize=lambda reply, req: "unused",
        say=lambda text: said.append(text) or asyncio.sleep(0),
        run_blocking=_passthrough,
    )
    _run(deliver, Payload("sid1", "x", "x", "x"))
    assert said == [delivery.FALLBACK]


def test_deliver_tags_non_focused_session_with_summary():
    said = []
    state = type("S", (), {
        "focused_session_id": "other-sid",
        "get_summary": lambda self, sid: "auth refactor",
    })()
    deliver = delivery.make_deliver(
        send_and_wait=lambda sid, text: None,
        fetch_last_reply=lambda sid: "done",
        summarize=lambda reply, req: "All set.",
        say=lambda text: said.append(text) or asyncio.sleep(0),
        voice_state=state,
        run_blocking=_passthrough,
    )
    _run(deliver, Payload("sid1", "x", "x", "x"))
    assert said == ["From your auth refactor session: All set."]


def test_deliver_does_not_tag_focused_session():
    said = []
    state = type("S", (), {
        "focused_session_id": "sid1",
        "get_summary": lambda self, sid: "auth refactor",
    })()
    deliver = delivery.make_deliver(
        send_and_wait=lambda sid, text: None,
        fetch_last_reply=lambda sid: "done",
        summarize=lambda reply, req: "All set.",
        say=lambda text: said.append(text) or asyncio.sleep(0),
        voice_state=state,
        run_blocking=_passthrough,
    )
    _run(deliver, Payload("sid1", "x", "x", "x"))
    assert said == ["All set."]
