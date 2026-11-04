"""The real model behind the LLM seam. Needs the optional extra: `uv sync --extra llm`, and ANTHROPIC_API_KEY in the environment."""

from typing import Any

from .models import LLM, TokenCounter

MODEL = "claude-haiku-5-5"
VERIFIER_MODEL = "claude-sonnet-5-5"  # stronger and dearer: used only to compare pairs of Items


def anthropic_llm(client: Any = None, model: str = MODEL, max_tokens: int = 1024) -> LLM:
    if client is None:
        from anthropic import Anthropic  # imported here: only installed with the `llm` extra

        client = Anthropic()  # reads ANTHROPIC_API_KEY; the SDK retries 429/5xx itself

    def call(prompt: str) -> str:
        response = client.messages.create(
            model=model, max_tokens=max_tokens, output_config={"effort": "low"}, messages=[{"role": "user", "content": prompt}]
        )
        return next((b.text for b in response.content if b.type == "text"), "")  # skip thinking blocks

    return call


def anthropic_counter(client: Any = None) -> TokenCounter:
    """Exact counts from Anthropic's counting endpoint. shortcut: each text is counted as a lone user message, so it includes a few
    tokens of message framing; upgrade if the absolute figure must match the live prompt."""
    if client is None:
        from anthropic import Anthropic

        client = Anthropic()

    return lambda texts: [
        client.messages.count_tokens(model=MODEL, messages=[{"role": "user", "content": text}]).input_tokens for text in texts
    ]
