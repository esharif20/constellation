import importlib

import pytest


@pytest.fixture(autouse=True)
def private_default_caches(tmp_path_factory, monkeypatch):
    """No test may read or write the real ~/.cache; each test gets fresh default cache files."""
    root = tmp_path_factory.mktemp("default-caches")
    for module, name in (("classify", "labels"), ("costs", "token-counts"), ("overlaps", "verdicts"), ("retrieve", "embeddings")):
        # import_module: `constellation.classify` as an attribute is the re-exported function, not the module
        monkeypatch.setattr(importlib.import_module(f"constellation.{module}"), "DEFAULT_CACHE", root / f"{name}.json")
    monkeypatch.setattr(importlib.import_module("constellation.review"), "DEFAULT_CHECKPOINT", root / "review.sqlite")
    monkeypatch.setattr(importlib.import_module("constellation.server"), "DEFAULT_CHECKLIST", root / "checklist.md")


@pytest.fixture(autouse=True)
def no_real_transcripts(monkeypatch):
    from pathlib import Path

    import constellation
    import constellation.usage as usage

    forbidden = (Path.home() / ".claude").resolve()
    original = usage.read_usage

    def guarded(config_dir, items, relations):
        assert not Path(config_dir).resolve().is_relative_to(forbidden), "real transcripts forbidden"
        return original(config_dir, items, relations)

    monkeypatch.setattr(usage, "read_usage", guarded)
    monkeypatch.setattr(constellation, "read_usage", guarded)


@pytest.fixture(autouse=True)
def no_real_lockfile(tmp_path_factory, monkeypatch):
    """No test may read the real ~/.agents: the default lockfile is an absent tmp path, and a read under the real one fails loudly."""
    from pathlib import Path

    import constellation.claude_code as claude_code
    import constellation.origins as origins

    forbidden = (Path.home() / ".agents").resolve()
    original = origins.read_lock
    monkeypatch.setattr(origins, "DEFAULT_LOCKFILE", tmp_path_factory.mktemp("no-agents") / ".skill-lock.json")

    def guarded(path, secrets):
        assert not Path(path).resolve().is_relative_to(forbidden), "real ~/.agents forbidden"
        return original(path, secrets)

    monkeypatch.setattr(origins, "read_lock", guarded)
    monkeypatch.setattr(claude_code, "read_lock", guarded)
