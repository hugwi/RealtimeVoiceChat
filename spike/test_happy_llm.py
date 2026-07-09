import asyncio
from livekit.agents.llm import ChatContext
import happy_bridge as hb
import happy_llm
from classifier import Classification


class _FakeDispatcher:
    def __init__(self):
        self.submitted = []

    def set_worker(self, worker):
        pass

    def submit(self, payload):
        self.submitted.append(payload)


def _collect(llm, ctx):
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


class _State:
    def __init__(self, focused=None):
        self.focused_session_id = focused
        self.transcript = []

    def append_transcript(self, text, *, max_turns=20):
        if text and text.strip():
            self.transcript.append(text.strip())

    def transcript_context(self):
        return "\n".join(self.transcript)

    def drain_transcript(self):
        text = "\n".join(self.transcript)
        self.transcript = []
        return text


def test_chitchat_speaks_reply_and_does_not_dispatch():
    disp = _FakeDispatcher()
    llm = happy_llm.HappyBridgeLLM(
        converse=lambda text, context="": "Doing well, what next?",
        classify=lambda text, context="": Classification(is_task=False),
        dispatcher=disp,
        resolve_session=lambda override=None, focused=None: "sid1",
        voice_state=_State(),
    )
    out = _collect(llm, _ctx("how are you"))
    assert out == "Doing well, what next?"
    assert disp.submitted == []


def test_task_dispatches_and_speaks_ack():
    disp = _FakeDispatcher()
    state = _State()
    llm = happy_llm.HappyBridgeLLM(
        converse=lambda text, context="": "unused",
        classify=lambda text, context="": Classification(is_task=True, instruction="commit and push"),
        dispatcher=disp,
        resolve_session=lambda override=None, focused=None: "sid1",
        voice_state=state,
    )
    out = _collect(llm, _ctx("commit everything and push it"))
    assert out == happy_llm.ACK
    assert len(disp.submitted) == 1
    p = disp.submitted[0]
    assert p.session_id == "sid1"
    assert p.instruction == "commit and push"
    assert p.user_request == "commit everything and push it"
    assert "commit everything and push it" in p.transcript


def test_classify_failure_degrades_to_raw_task():
    disp = _FakeDispatcher()

    def boom_classify(text, context=""):
        raise RuntimeError("ollama down")

    llm = happy_llm.HappyBridgeLLM(
        converse=lambda text, context="": "unused",
        classify=boom_classify,
        dispatcher=disp,
        resolve_session=lambda override=None, focused=None: "sid1",
        voice_state=_State(),
    )
    out = _collect(llm, _ctx("please refactor the auth module"))
    assert out == happy_llm.ACK
    assert len(disp.submitted) == 1
    p = disp.submitted[0]
    assert p.instruction == "please refactor the auth module"
    assert "please refactor the auth module" in p.transcript


def test_task_speaks_error_when_session_unresolvable():
    disp = _FakeDispatcher()

    def no_session(override=None, focused=None):
        raise hb.HappyAgentError("no active Claude session found")

    llm = happy_llm.HappyBridgeLLM(
        converse=lambda text, context="": "unused",
        classify=lambda text, context="": Classification(is_task=True, instruction="do it"),
        dispatcher=disp,
        resolve_session=no_session,
        voice_state=_State(),
    )
    out = _collect(llm, _ctx("do the thing"))
    assert "session" in out.lower()
    assert disp.submitted == []


def test_empty_conversational_reply_falls_back():
    disp = _FakeDispatcher()
    llm = happy_llm.HappyBridgeLLM(
        converse=lambda text, context="": "",
        classify=lambda text, context="": Classification(is_task=False),
        dispatcher=disp,
        resolve_session=lambda override=None, focused=None: "sid1",
        voice_state=_State(),
    )
    out = _collect(llm, _ctx("mm"))
    assert out.strip() != ""


def test_task_uses_focused_session_from_voice_state():
    disp = _FakeDispatcher()
    seen = {}
    llm = happy_llm.HappyBridgeLLM(
        converse=lambda text, context="": "unused",
        classify=lambda text, context="": Classification(is_task=True, instruction="go"),
        dispatcher=disp,
        resolve_session=lambda override=None, focused=None: seen.setdefault("focused", focused) or "sid",
        voice_state=_State(focused="focus-sid"),
    )
    _collect(llm, _ctx("go do it"))
    assert seen["focused"] == "focus-sid"


def test_task_override_passed_to_resolver():
    disp = _FakeDispatcher()
    seen = {}
    llm = happy_llm.HappyBridgeLLM(
        converse=lambda text, context="": "unused",
        classify=lambda text, context="": Classification(is_task=True, instruction="go"),
        dispatcher=disp,
        resolve_session=lambda override=None, focused=None: seen.setdefault("override", override) or "sid",
        session_override="forced-sid",
        voice_state=_State(focused="focus-sid"),
    )
    _collect(llm, _ctx("go"))
    assert seen["override"] == "forced-sid"
