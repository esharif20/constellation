"""The real local embedder (ADR 0003: no text leaves the machine). Needs the optional extra: `uv sync --extra local`."""

from typing import Any

from .models import Embedder

MODEL = "BAAI/bge-small-en-v1.5"


def fastembed_embedder() -> Embedder:
    model: Any = None  # loaded on first use, so a blocked download or a missing install is reported as a warning, not a crash

    def embed(texts: list[str]) -> list[list[float]]:
        nonlocal model
        if model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError:
                raise RuntimeError("fastembed is not installed; run `uv sync --extra local`") from None
            model = TextEmbedding(model_name=MODEL)
        return [vector.tolist() for vector in model.embed(texts)]

    return embed
