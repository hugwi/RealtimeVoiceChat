import classifier


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


def test_classify_detects_task_and_instruction():
    client = _FakeClient(content='{"is_task": true, "instruction": "commit and push"}')
    c = classifier.classify("hey, commit everything and push", client=client)
    assert c.is_task is True
    assert c.instruction == "commit and push"


def test_classify_detects_chitchat():
    client = _FakeClient(content='{"is_task": false, "instruction": ""}')
    c = classifier.classify("how's it going", client=client)
    assert c.is_task is False


def test_classify_unparseable_output_defaults_to_chitchat():
    client = _FakeClient(content="I think you want to commit")
    c = classifier.classify("commit please", client=client)
    assert c.is_task is False


def test_classify_reraises_on_client_error():
    client = _FakeClient(error=RuntimeError("ollama down"))
    import pytest
    with pytest.raises(RuntimeError):
        classifier.classify("do a thing", client=client)
