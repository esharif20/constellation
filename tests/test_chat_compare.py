import json
import time

import pytest
from fakes_search import GROUPS
from fastapi.testclient import TestClient

from constellation import server

ITEMS = [
    {
        "id": "pt",
        "kind": "skill",
        "name": "ponytail",
        "description": "Writes the smallest working diff. Also reviews code. Secret sk-ant-api03-abcdefghijklmnop",
    },
    {"id": "ch", "kind": "agent", "name": "chisel", "description": "Trims code to the bare minimum"},
    {"id": "wr", "kind": "skill", "name": "chisel-wrap", "description": "Calls chisel for you"},
    {"id": "dup", "kind": "skill", "name": "ponytail-copy", "description": "Writes the smallest working diff"},
    {"id": "mid", "kind": "agent", "name": "midway", "description": "Half of what ponytail does"},
    {"id": "hook", "kind": "hook", "name": "stop-hook", "description": ""},
    {"id": "slides", "kind": "skill", "name": "deck-maker", "description": "Builds a presentation"},
]
DATA = {
    "items": ITEMS,
    "costs": {"pt": {"always_on": 1200, "on_use": 3000}, "ch": {"always_on": None, "on_use": None}, "wr": {"always_on": 0, "on_use": 5}},
    "overlaps": [
        {"a_id": "pt", "b_id": "dup", "verdict": "duplicate", "reason": "Same job"},
        {"a_id": "wr", "b_id": "ch", "verdict": "wrapper", "reason": "Only calls chisel"},
        {"a_id": "pt", "b_id": "mid", "verdict": "overlap", "reason": "Some shared work"},
        {"a_id": "pt", "b_id": "slides", "verdict": "distinct", "reason": "Unrelated"},
    ],
    "usage": {
        "pt": {"count": 4, "last_used": "2026-10-30T10:00:00Z"},
        "ch": {"count": 0, "last_used": None},
        "wr": {"count": 1, "last_used": None},
    },
    "usage_window": {"files": 3, "first": "2026-10-01", "last": "2026-10-30", "skipped": 0},
    "clusters": [{"name": "code trimming", "item_ids": ["pt", "dup", "ch"]}, {"name": "decks", "item_ids": ["slides"]}],
}


AXES: dict[str, int] = {}


def concept_embedder(texts):
    """Concept groups as in fakes_search plus a private axis per text, so unrelated texts are not similar."""
    out = []
    for text in texts:
        words = set(text.lower().replace(":", " ").split())
        axis = AXES.setdefault(text, len(AXES))
        out.append([3.0 * len(words & g) for g in GROUPS] + [1.0 if n == axis else 0.0 for n in range(300)])
    return out


def make(tmp_path, monkeypatch, data):
    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    monkeypatch.setattr(server, "STATIC", static)
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(data))
    return TestClient(server.create_app(path, checklist=tmp_path / "c.md", embedder=concept_embedder), base_url="http://127.0.0.1:8765")


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make(tmp_path, monkeypatch, DATA)


def ask(client, question, **body):
    response = client.post("/api/chat", json={"question": question, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_authors_typo_question_resolves_ponytail_and_the_closest_second_item(client):
    # "shovel" has no name or meaning match, so the weak guess is the only Item whose letters fit: use a near name instead
    reply = ask(client, "wht is pony tail an how does I t compare to chisle")
    lines = reply["answer"].split("\n")
    assert lines[0] == "ponytail vs chisel"
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt", "ch"]}]
    assert "Did you mean" not in reply["answer"]  # "chisle" is one edit from chisel: a strong typo match


def test_weak_second_match_asks_did_you_mean_and_still_compares(client):
    reply = ask(client, "wht is pony tail an how does I t compare to chsl")
    assert reply["answer"].startswith('Did you mean chisel? "chsl" is not an exact match.\nponytail vs chisel\n')
    assert reply["actions"][0]["item_ids"] == ["pt", "ch"]


def test_full_side_by_side(client):
    answer = ask(client, "compare ponytail to chisel")["answer"]
    assert answer == "\n".join(
        [
            "ponytail vs chisel",
            "",
            "ponytail",
            "- Kind: skill",
            "- Does: Writes the smallest working diff.",
            "- Always-on: 1,200 tokens",
            "- On-use: 3,000 tokens",
            "- Usage: 4 uses, last 2026-10-30",
            "- Cluster: code trimming",
            "",
            "chisel",
            "- Kind: agent",
            "- Does: Trims code to the bare minimum",
            "- Always-on: unknown",
            "- On-use: unknown",
            "- Usage: never seen in 30 days",
            "- Cluster: code trimming",
            "",
            "Overlap: none recorded in this scan",
            "Clusters: same cluster",
            "Suggestion: different jobs",
        ]
    )


@pytest.mark.parametrize(
    "question",
    [
        "ponytail vs chisel",
        "Ponytail VS. chisel?",
        "difference between ponytail and chisel",
        "what is the difference between ponytail and chisel",
        "how does ponytail compare to chisel",
        "compare ponytail with chisel",
        "compare ponytail and chisel",
        "comparing ponytail against chisel",
    ],
)
def test_every_compare_phrasing(client, question):
    reply = ask(client, question)
    assert reply["answer"].startswith("ponytail vs chisel\n")
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt", "ch"]}]


def test_recommendations_follow_the_overlap_verdict(client):
    assert ask(client, "ponytail vs ponytail-copy")["answer"].endswith(
        "Overlap: duplicate: Same job\nClusters: same cluster\nSuggestion: duplicate: keep one"
    )
    wrapper = ask(client, "chisel-wrap vs chisel")["answer"]
    assert "Suggestion: wrapper: keep the wrapped one (chisel); chisel-wrap only calls it" in wrapper
    assert "Suggestion: wrapper: keep the wrapped one (chisel)" in ask(client, "chisel vs chisel-wrap")["answer"]
    assert ask(client, "ponytail vs midway")["answer"].endswith("Suggestion: partial overlap: keep both only if you need the difference")
    distinct = ask(client, "ponytail vs deck-maker")["answer"]
    assert "Overlap: distinct: Unrelated\nClusters: different clusters\nSuggestion: different jobs" in distinct


def test_usage_and_cost_edge_cases(client):
    answer = ask(client, "chisel-wrap vs stop-hook")["answer"]
    assert "- Always-on: 0 tokens" in answer and "- On-use: 5 tokens" in answer
    assert "- Usage: 1 use\n" in answer
    assert answer.count("- Usage: unknown (not read for this Item)") == 1
    assert "- Does: no description" in answer
    assert "Clusters: cluster unknown" in answer


def test_usage_absent_everywhere(tmp_path, monkeypatch):
    data = {k: v for k, v in DATA.items() if k not in ("usage", "usage_window", "clusters", "overlaps", "costs")}
    answer = ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")["answer"]
    assert answer.count("- Usage: unknown (not read for this Item)") == 2
    assert answer.count("- Always-on: unknown") == 2 and "Cluster:" not in answer


def test_never_seen_without_a_window_span_and_empty_transcripts(tmp_path, monkeypatch):
    data = {**DATA, "usage_window": {"files": 2, "first": None, "last": None, "skipped": 0}}
    assert "- Usage: never seen in the scanned transcripts" in ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")["answer"]
    data = {**DATA, "usage_window": {"files": 0, "first": None, "last": None, "skipped": 0}}
    assert "never seen" not in ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")["answer"]


def test_use_with_missing_last_date(tmp_path, monkeypatch):
    data = {**DATA, "usage": {"pt": {"count": 2, "last_used": None}}}
    assert "- Usage: 2 uses\n" in ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")["answer"]


def test_missing_second_item_explains_the_first(client):
    reply = ask(client, "ponytail vs zzzqqq")
    assert reply["answer"].startswith(
        'I could not find an Item matching "zzzqqq" to compare with. Here is ponytail:\n\nponytail\n- Kind: skill'
    )
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt"]}]


def test_unresolvable_first_item_or_same_item_twice(client):
    for question in ("zzzqqq vs ponytail", "ponytail vs ponytail", "how does it compare to ponytail"):
        reply = ask(client, question)
        assert reply["answer"].startswith("Name two Items to compare") and reply["actions"] == []


def test_it_means_the_selected_item(client):
    reply = ask(client, "how does it compare to chisel", selected_ids=["pt"])
    assert reply["answer"].startswith("ponytail vs chisel\n")
    assert ask(client, "how does it compare to chisel", selected_ids=["ch"])["answer"].startswith("Name two Items")


def test_what_is_is_a_short_card_not_a_dump(client):
    for question in (
        "what is ponytail?",
        "wht is pony tail",
        "What's ponytail",
        "explain ponytail",
        "describe the ponytail",
        "tell me about ponytail",
    ):
        reply = ask(client, question)
        assert reply["answer"] == "\n".join(
            [
                "ponytail",
                "- Kind: skill",
                "- Does: Writes the smallest working diff.",
                "- Always-on: 1,200 tokens",
                "- On-use: 3,000 tokens",
                "- Usage: 4 uses, last 2026-10-30",
                "- Cluster: code trimming",
                "- Duplicate with ponytail-copy",
                "- Overlap with midway",
            ]
        )
        assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt"]}]


def test_what_is_weak_or_missing(client):
    assert ask(client, "what is chsl")["answer"].startswith('Did you mean chisel? "chsl" is not an exact match.\nchisel\n')
    assert (
        ask(client, "what is zzzqqq")["answer"]
        == 'I could not find an Item matching "zzzqqq". Try an Item name or a word from its description.'
    )


def test_meaning_finds_the_second_item_once_vectors_are_ready(client):
    for _ in range(100):  # vectors are built in a background thread
        answer = ask(client, "ponytail vs presentation")["answer"]
        if answer.startswith("ponytail vs deck-maker"):
            break
        time.sleep(0.05)
    assert answer.startswith("ponytail vs deck-maker") or answer.startswith("Did you mean deck-maker?")


def test_answers_are_redacted_and_cached(client):
    first = ask(client, "what is ponytail")
    assert "sk-ant" not in first["answer"] and first["cached"] is False
    for _ in range(100):  # the first answers may predate the background vectors, which are part of the cache key
        if ask(client, "what is ponytail")["cached"]:
            break
        time.sleep(0.05)
    else:
        pytest.fail("never cached")
    assert "sk-ant" not in ask(client, "ponytail sk-ant-api03-abcdefghijklmnop vs chisel")["answer"]


def test_other_chat_questions_are_unchanged(client):
    assert ask(client, "what is the total always-on cost?")["answer"].startswith("Local chat ranks")
    assert ask(client, "what is this?", selected_ids=["pt"])["answer"].startswith("Item details:")
    assert ask(client, "how many items are there")["answer"] == "The current scan contains 7 Items."


def test_explain_with_a_cost_word_uses_the_selected_item(client):
    for question in ("Explain the cost", "Describe the tokens"):
        assert ask(client, question, selected_ids=["pt"])["answer"].startswith("Item details:\n- ponytail (skill)")


def test_a_named_first_item_beats_the_selection(client):
    assert ask(client, "ponytail vs chisel", selected_ids=["ch"])["answer"].startswith("ponytail vs chisel\n")
    assert ask(client, "it vs chisel", selected_ids=["pt"])["answer"].startswith("ponytail vs chisel\n")


def test_both_weak_matches_each_get_a_note(client):
    answer = ask(client, "ponytl vs chsl")["answer"]
    assert answer.startswith(
        'Did you mean ponytail? "ponytl" is not an exact match.\nDid you mean chisel? "chsl" is not an exact match.\nponytail vs chisel\n'
    )


def test_answer_before_vectors_is_not_reused_after_they_arrive(tmp_path, monkeypatch):
    import threading

    gate = threading.Event()

    def slow(texts):
        gate.wait(5)
        return concept_embedder(texts)

    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(server, "STATIC", static)
    (tmp_path / "scan.json").write_text(json.dumps(DATA))
    app = TestClient(
        server.create_app(tmp_path / "scan.json", checklist=tmp_path / "c.md", embedder=slow), base_url="http://127.0.0.1:8765"
    )
    before = ask(app, "ponytail vs pptx")["answer"]
    assert before.startswith("I could not find")
    gate.set()
    for _ in range(100):
        after = ask(app, "ponytail vs pptx")
        if after["answer"] != before:
            break
        time.sleep(0.05)
    assert after["cached"] is False and "deck-maker" in after["answer"]
