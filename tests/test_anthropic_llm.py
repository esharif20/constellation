from types import SimpleNamespace

from constellation.anthropic_llm import anthropic_llm


class FakeClient:
    """Stands in for anthropic.Anthropic: records the request and replies with a thinking block then a text block."""

    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="Deploys apps")])


def test_sends_the_prompt_to_the_model_and_returns_the_text():
    client = FakeClient()

    reply = anthropic_llm(client=client)("What does X do?")

    assert reply == "Deploys apps"
    assert client.calls[0]["model"] == "claude-haiku-5-5"
    assert client.calls[0]["messages"] == [{"role": "user", "content": "What does X do?"}]
