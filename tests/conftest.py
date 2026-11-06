import importlib
from pathlib import Path

import pytest

_REAL_CLAUDE = (Path.home() / ".claude").resolve()


@pytest.fixture(autouse=True)
def no_external_tracing(monkeypatch):
    """Every test stays offline, including mutants that enable LangSmith tracing."""
    import requests
    from langsmith import run_trees, tracing_context
    from langsmith.client import Client

    class RecordingClient(Client):
        def __init__(self):
            self.calls = 0

        def create_run(self, *args, **kwargs):
            self.calls += 1

        def update_run(self, *args, **kwargs):
            self.calls += 1

    client = RecordingClient()

    def forbidden(*args, **kwargs):
        pytest.fail("A real tracing client or external HTTP transport must never be used")

    monkeypatch.setattr(Client, "__init__", forbidden)
    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(run_trees, "get_cached_client", lambda **kwargs: client)
    monkeypatch.setattr(run_trees, "_get_write_replicas_from_env", lambda: [])
    with tracing_context(enabled=False, client=client):
        yield client
    assert client.calls == 0, "The application must disable external tracing"


@pytest.fixture(autouse=True)
def private_default_caches(tmp_path_factory, monkeypatch):
    """No test may read or write the real ~/.cache; each test gets fresh default cache files."""
    root = tmp_path_factory.mktemp("default-caches")
    monkeypatch.setenv("HOME", str(root))
    for module, name in (
        ("classify", "labels"),
        ("costs", "token-counts"),
        ("overlaps", "verdicts"),
        ("retrieve", "embeddings"),
        ("history", "history"),
        ("habits", "habits"),
        ("pins", "pins"),
    ):
        # import_module: `constellation.classify` as an attribute is the re-exported function, not the module
        monkeypatch.setattr(importlib.import_module(f"constellation.{module}"), "DEFAULT_CACHE", root / f"{name}.json")
    monkeypatch.setattr(importlib.import_module("constellation.review"), "DEFAULT_CHECKPOINT", root / "review.sqlite")
    monkeypatch.setattr(importlib.import_module("constellation.scan_graph"), "DEFAULT_CHECKPOINT", root / "scan.sqlite")
    monkeypatch.setattr(importlib.import_module("constellation.server"), "DEFAULT_CHECKLIST", root / "checklist.md")


@pytest.fixture(autouse=True)
def no_real_transcripts(monkeypatch):
    from pathlib import Path

    import constellation
    import constellation.usage as usage

    forbidden = _REAL_CLAUDE
    original = usage.read_usage

    def guarded(config_dir, items, relations, project=None, home=None):
        assert not Path(config_dir).resolve().is_relative_to(forbidden), "real transcripts forbidden"
        return original(config_dir, items, relations, project, home)

    monkeypatch.setattr(usage, "read_usage", guarded)
    fresh = usage.read_fresh

    def guarded_fresh(config_dir, items, relations, salt):
        assert not Path(config_dir).resolve().is_relative_to(forbidden), "real transcripts forbidden"
        return fresh(config_dir, items, relations, salt)

    monkeypatch.setattr(usage, "read_fresh", guarded_fresh)
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
