import hashlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from fakes import FakeCounter

from constellation import scan
from constellation.anthropic_llm import anthropic_counter
from constellation.models import Cost

FIXTURE = Path(__file__).parent / "fixtures" / "claude_config"


def cost_of(constellation, kind, name):
    return constellation.costs[next(i.id for i in constellation.items if i.kind == kind and i.name == name)]


def test_skills_and_agents_get_always_on_from_name_and_description_and_on_use_from_the_body(tmp_path):
    result = scan(FIXTURE, counter=FakeCounter(), cost_cache=tmp_path / "c.json", count_bodies=True)

    assert cost_of(result, "skill", "alpha") == Cost(always_on=7, on_use=4)  # "# Alpha\nFull instructions." is the body
    assert cost_of(result, "agent", "reviewer") == Cost(always_on=8, on_use=5)  # "You are a code reviewer."


def test_servers_and_connectors_have_only_an_always_on_cost(tmp_path):
    result = scan(FIXTURE, counter=FakeCounter(), cost_cache=tmp_path / "c.json")

    assert cost_of(result, "mcp_server", "localdb") == Cost(always_on=4, on_use=None)
    assert cost_of(result, "connector", "docs").on_use is None


def test_hook_costs_are_unknown_not_guessed(tmp_path):
    counter = FakeCounter()
    result = scan(FIXTURE, counter=counter, cost_cache=tmp_path / "c.json")

    hooks = [i for i in result.items if i.kind == "hook"]
    assert hooks and all(result.costs[h.id] == Cost(None, None) for h in hooks)
    assert not any("echo session started" in t for t in counter.texts)


def test_a_second_scan_of_an_unchanged_setup_makes_no_counting_calls(tmp_path):
    cache = tmp_path / "c.json"
    first = scan(FIXTURE, counter=FakeCounter(), cost_cache=cache)
    counter = FakeCounter()

    second = scan(FIXTURE, counter=counter, cost_cache=cache)

    assert counter.texts == []
    assert second.costs == first.costs


def test_the_cache_is_private_and_only_new_texts_are_counted(tmp_path):
    cache = tmp_path / "a" / "b" / "c.json"
    scan(FIXTURE, counter=FakeCounter(), cost_cache=cache, count_bodies=True)
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    counts = json.loads(cache.read_text())
    cache.write_text(json.dumps(dict(list(counts.items())[1:])))  # forget one text
    counter = FakeCounter()

    result = scan(FIXTURE, counter=counter, cost_cache=cache, count_bodies=True)

    assert len(counter.texts) == 1
    assert cost_of(result, "skill", "alpha") == Cost(7, 4)
    assert len(json.loads(cache.read_text())) == len(counts)  # earlier entries are kept, not replaced


def test_a_counter_that_returns_the_wrong_number_of_counts_is_a_bug_not_a_warning(tmp_path):
    with pytest.raises(ValueError):
        scan(FIXTURE, counter=lambda texts: [1], cost_cache=tmp_path / "c.json")


def test_a_corrupt_cache_is_recounted(tmp_path):
    cache = tmp_path / "c.json"
    cache.write_text("not json")

    result = scan(FIXTURE, counter=FakeCounter(), cost_cache=cache)

    assert cost_of(result, "skill", "alpha").always_on is not None


def test_a_planted_secret_never_reaches_the_counter(tmp_path):
    config = tmp_path / "cfg"
    skill = config / "skills" / "leaky"
    skill.mkdir(parents=True)
    secret = "hunter2hunter2"  # low entropy: only the .env lookup can catch it
    (skill / "SKILL.md").write_text(f"---\nname: leaky\ndescription: Uses {secret} here\n---\nbody {secret}\n")
    (config / ".env").write_text(f"TOKEN={secret}\n")
    counter = FakeCounter()

    scan(config, counter=counter, cost_cache=tmp_path / "c.json", count_bodies=True)

    assert counter.texts and not any(secret in t for t in counter.texts)
    leaky = next(t for t in counter.texts if "Uses" in t)
    assert hashlib.sha256(leaky.encode()).hexdigest() in (tmp_path / "c.json").read_text()  # keyed on the redacted text


def test_a_failing_counter_gives_a_warning_and_unknown_costs(tmp_path):
    result = scan(FIXTURE, counter=FakeCounter(fail_with="boom"), cost_cache=tmp_path / "c.json")

    assert "could not count context cost: ConnectionError: boom" in result.warnings
    assert cost_of(result, "skill", "alpha") == Cost(None, None)
    assert not (tmp_path / "c.json").exists()


def test_no_counter_means_no_costs():
    assert scan(FIXTURE).costs == {}


def test_the_anthropic_counter_asks_the_counting_endpoint_once_per_text():
    calls = []

    def count_tokens(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(input_tokens=len(calls) * 10)

    client = SimpleNamespace(messages=SimpleNamespace(count_tokens=count_tokens))

    assert anthropic_counter(client=client)(["a", "b"]) == [10, 20]
    assert calls[0]["model"] == "claude-haiku-5-5"
    assert calls[0]["messages"] == [{"role": "user", "content": "a"}]


def test_an_unwritable_cache_is_a_warning_and_the_counts_are_kept(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")

    result = scan(FIXTURE, counter=FakeCounter(), cost_cache=blocker / "c.json")

    assert cost_of(result, "skill", "alpha").always_on is not None
    assert any("could not save the token-count cache" in w for w in result.warnings)


def test_by_default_no_skill_body_is_counted_so_none_leaves_the_machine_and_on_use_is_unknown(tmp_path):
    counter = FakeCounter()

    result = scan(FIXTURE, counter=counter, cost_cache=tmp_path / "c.json")

    assert not any("Full instructions" in t or "You are a code reviewer" in t for t in counter.texts)
    assert cost_of(result, "skill", "alpha") == Cost(always_on=7, on_use=None)
