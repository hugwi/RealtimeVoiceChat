import summarizer as s


class _FakeMessage:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _FakeCompletions:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return type("R", (), {"choices": [_FakeMessage(self._content)]})


class _FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = type("C", (), {"completions": _FakeCompletions(content, error)})


def test_summarize_returns_model_output():
    client = _FakeClient(content="Committed and opened PR 12.")
    assert s.summarize("long claude reply", client=client) == "Committed and opened PR 12."


def test_summarize_blank_reply_returns_placeholder():
    client = _FakeClient(content="should not be used")
    out = s.summarize("   ", client=client)
    assert "check the chat" in out.lower() or "nothing" in out.lower()


def test_summarize_falls_back_to_truncation_on_error():
    reply = "First sentence. Second sentence. Third sentence. Fourth sentence."
    client = _FakeClient(error=RuntimeError("ollama down"))
    out = s.summarize(reply, client=client)
    assert out.startswith("First sentence.")
    assert "Fourth sentence." not in out


def test_summarize_never_raises_on_empty_model_output():
    reply = "Alpha. Beta. Gamma."
    client = _FakeClient(content="")
    out = s.summarize(reply, client=client)
    assert out.startswith("Alpha.")
