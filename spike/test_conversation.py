import conversation


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


def test_converse_returns_model_reply():
    client = _FakeClient(content="Doing great, what are we building?")
    assert conversation.converse("how are you", client=client) == "Doing great, what are we building?"


def test_converse_returns_empty_on_error():
    client = _FakeClient(error=RuntimeError("ollama down"))
    assert conversation.converse("hi", client=client) == ""


def test_converse_strips_whitespace():
    client = _FakeClient(content="  hello  ")
    assert conversation.converse("hi", client=client) == "hello"
