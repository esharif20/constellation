import threading
import time


class FakeLLM:
    """Stand-in for the real model: returns a canned label per item name and records every prompt it receives."""

    def __init__(self, labels: dict[str, str], default: str = "other", fail_for: dict[str, str] | None = None):
        self.labels, self.default, self.fail_for, self.prompts = labels, default, fail_for or {}, []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        for name, message in self.fail_for.items():  # item name -> message of the ConnectionError its call raises
            if f"Name: {name}\n" in prompt:
                raise ConnectionError(message)
        for name, label in self.labels.items():
            if f"Name: {name}\n" in prompt:
                return label
        return self.default


class FakeEmbedder:
    """Stand-in for the embedding model: the first keyword found in a text picks its vector; records every text it receives."""

    def __init__(self, vectors: dict[str, list[float]], default: list[float] | None = None, fail_with: str | None = None):
        self.vectors, self.default, self.fail_with, self.texts = vectors, default or [0.0, 0.0, 1.0], fail_with, []

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        if self.fail_with:
            raise ConnectionError(self.fail_with)
        return [next((v for kw, v in self.vectors.items() if kw in t), self.default) for t in texts]


class SlowLLM:
    """Takes a moment per call and records the most calls in flight at once."""

    def __init__(self, seconds: float = 0.05):
        self.seconds, self.now, self.peak, self.lock = seconds, 0, 0, threading.Lock()

    def __call__(self, prompt: str) -> str:
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
        time.sleep(self.seconds)
        with self.lock:
            self.now -= 1
        return "label"


class FakeCounter:
    """Stand-in for the counting endpoint: a text's count is its word count; records every text it receives."""

    def __init__(self, fail_with: str | None = None):
        self.fail_with, self.texts = fail_with, []

    def __call__(self, texts: list[str]) -> list[int]:
        self.texts.extend(texts)
        if self.fail_with:
            raise ConnectionError(self.fail_with)
        return [len(t.split()) for t in texts]
