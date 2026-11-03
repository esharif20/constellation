"""The real local embedder (ADR 0003: no text leaves the machine). Needs the optional extra: `uv sync --extra local`."""

from .models import Embedder

MODEL = "BAAI/bge-small-en-v1.5"


def fastembed_embedder() -> Embedder:
    from fastembed import TextEmbedding  # imported here: heavy, and only installed with the `local` extra

    model = TextEmbedding(model_name=MODEL)
    return lambda texts: [vector.tolist() for vector in model.embed(texts)]
