class FakeLLM:
    """Stand-in for the real model: returns a canned label per item name and records every prompt it receives."""

    def __init__(self, labels: dict[str, str], default: str = "other"):
        self.labels, self.default, self.prompts = labels, default, []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for name, label in self.labels.items():
            if f"Name: {name}\n" in prompt:
                return label
        return self.default


class FakeEmbedder:
    """Stand-in for the embedding model: the first keyword found in a text picks its vector; records every text it receives."""

    def __init__(self, vectors: dict[str, list[float]], default: list[float] | None = None):
        self.vectors, self.default, self.texts = vectors, default or [0.0, 0.0, 1.0], []

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return [next((v for kw, v in self.vectors.items() if kw in t), self.default) for t in texts]
