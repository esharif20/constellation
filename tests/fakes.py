import json
import re
import threading
import time


def write_skill(root, name, body, description="Does a thing"):
    """A skill file under `root` (a config dir or a plugin dir) with the given body."""
    (root / "skills" / name).mkdir(parents=True, exist_ok=True)
    (root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n")


def pairs(constellation):
    """(a name, b name, verdict) per Overlap, in the Constellation's order."""
    return [(o.a_id.rsplit(":", 1)[-1], o.b_id.rsplit(":", 1)[-1], o.verdict) for o in constellation.overlaps]


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


class FakeVerifier:
    """Stand-in for the strong model: replies per pair of item names (or a default), records every prompt, and tracks concurrency."""

    def __init__(
        self,
        replies: dict[frozenset[str], str] | None = None,
        default: str | None = None,
        fail_for: dict[str, str] | None = None,
        seconds: float = 0.0,
    ):
        self.replies, self.fail_for, self.seconds, self.prompts = replies or {}, fail_for or {}, seconds, []
        self.default = default or json.dumps({"verdict": "distinct", "reason": "different jobs"})
        self.now, self.peak, self.lock = 0, 0, threading.Lock()

    def __call__(self, prompt: str) -> str:
        names = frozenset(re.findall(r"^Name: (.*)$", prompt, re.MULTILINE))
        with self.lock:
            self.prompts.append(prompt)
            self.now += 1
            self.peak = max(self.peak, self.now)
        time.sleep(self.seconds)
        with self.lock:
            self.now -= 1
        for name, message in self.fail_for.items():
            if name in names:
                raise ConnectionError(message)
        return self.replies.get(names, self.default)


def verdict(kind: str, reason: str = "because", **extra: str) -> str:
    return json.dumps({"verdict": kind, "reason": reason, **extra})
