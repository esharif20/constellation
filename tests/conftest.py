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
