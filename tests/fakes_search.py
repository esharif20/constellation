"""A deterministic fake embedder: words in the same concept group share a dimension, so meaning is testable without a model."""

GROUPS = [{"email", "gmail", "mail", "inbox"}, {"slides", "deck", "presentation", "pptx"}, {"test", "tests", "testing"}]


def concept_embedder(texts: list[str]) -> list[list[float]]:
    out = []
    for text in texts:
        words = set(text.lower().replace(":", " ").split())
        out.append([float(len(words & g)) + 0.01 for g in GROUPS])
    return out
