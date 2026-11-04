import importlib

import pytest


@pytest.fixture(autouse=True)
def private_default_caches(tmp_path_factory, monkeypatch):
    """No test may read or write the real ~/.cache; each test gets fresh default cache files."""
    root = tmp_path_factory.mktemp("default-caches")
    for module, name in (("classify", "labels"), ("costs", "token-counts"), ("overlaps", "verdicts")):
        # import_module: `constellation.classify` as an attribute is the re-exported function, not the module
        monkeypatch.setattr(importlib.import_module(f"constellation.{module}"), "DEFAULT_CACHE", root / f"{name}.json")
    monkeypatch.setattr(importlib.import_module("constellation.review"), "DEFAULT_CHECKPOINT", root / "review.sqlite")


@pytest.fixture(autouse=True)
def no_real_transcripts(monkeypatch):
    from pathlib import Path

    import constellation
    import constellation.usage as usage

    forbidden = (Path.home() / ".claude").resolve()
    original = usage.read_usage

    def guarded(config_dir, items):
        assert not Path(config_dir).resolve().is_relative_to(forbidden), "real transcripts forbidden"
        return original(config_dir, items)

    monkeypatch.setattr(usage, "read_usage", guarded)
    monkeypatch.setattr(constellation, "read_usage", guarded)
