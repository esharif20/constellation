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


def test_the_verifier_model_and_token_cap_can_be_chosen():
    from constellation.anthropic_llm import VERIFIER_MODEL

    client = FakeClient()

    anthropic_llm(client=client, model=VERIFIER_MODEL, max_tokens=2048)("Compare these.")

    assert VERIFIER_MODEL == "claude-sonnet-5-5"
    assert client.calls[0]["model"] == "claude-sonnet-5-5" and client.calls[0]["max_tokens"] == 2048
    assert client.calls[0]["output_config"] == {"effort": "low"}


def test_the_default_cap_is_unchanged():
    client = FakeClient()

    anthropic_llm(client=client)("x")

    assert client.calls[0]["max_tokens"] == 1024
