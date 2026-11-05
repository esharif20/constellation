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


def names(reply):
    return [c["name"] for c in reply["blocks"]["cards"]]


def test_the_authors_typo_question_resolves_ponytail_and_the_closest_second_item(client):
    reply = ask(client, "wht is pony tail an how does I t compare to chisle")
    assert reply["answer"].startswith("ponytail and chisel do different jobs.\n")
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt", "ch"]}]
    assert reply["blocks"]["note"] is None  # "chisle" is one edit from chisel: a strong typo match


def test_one_weak_second_match_is_taken_and_said_so(client):
    reply = ask(client, "ponytail vs dckmkr")
    assert names(reply) == ["ponytail", "deck-maker"]
    assert reply["blocks"]["note"] == 'I took "dckmkr" to mean deck-maker.'


def test_several_equally_close_matches_ask_which_one(client):
    reply = ask(client, "wht is pony tail an how does I t compare to chsl")
    assert reply["answer"] == "Which one did you mean?" and reply["actions"] == []
    assert reply["blocks"]["cards"] == []
    assert reply["blocks"]["did_you_mean"] == [
        {"id": "ch", "name": "chisel", "ask": "Compare ponytail and chisel"},
        {"id": "wr", "name": "chisel-wrap", "ask": "Compare ponytail and chisel-wrap"},
    ]
    assert [d["ask"] for d in ask(client, "chsl vs ponytail")["blocks"]["did_you_mean"]][0] == "Compare chisel and ponytail"
    assert ask(client, "ponytail vs chsl")["blocks"]["did_you_mean"][0]["ask"] == "Compare ponytail and chisel"
    assert ask(client, ask(client, "ponytail vs chsl")["blocks"]["did_you_mean"][1]["ask"])["blocks"]["cards"][1]["name"] == "chisel-wrap"


def test_full_side_by_side(client):
    reply = ask(client, "compare ponytail to chisel")
    assert reply["answer"] == "\n".join(
        [
            "ponytail and chisel do different jobs.",
            "Kind: skill | agent",
            "What it does: Writes the smallest working diff. | Trims code to the bare minimum",
            "Every session: 1,200 tokens | unknown",
            "When used: 3,000 tokens | unknown",
            "Usage: Used 4 times in 30 days, last used 30 Oct | Not seen in 30 days",
            "Same cluster: yes",
        ]
    )
    assert reply["blocks"]["compare"]["same_cluster"] is True and len(reply["blocks"]["cards"]) == 2
    assert reply["blocks"]["follow_ups"] == ["Should I keep ponytail?", "Should I keep chisel?"]


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
    assert reply["answer"].startswith("ponytail and chisel do different jobs.\n")
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt", "ch"]}]


def test_headline_and_verdicts_follow_the_overlap(client):
    assert ask(client, "ponytail vs ponytail-copy")["answer"].startswith("ponytail and ponytail-copy do the same job; you could keep one.")
    wrapper = ask(client, "chisel-wrap vs chisel")
    assert wrapper["answer"].startswith("chisel-wrap only calls chisel; you could keep the wrapped one.")
    assert ask(client, "chisel vs chisel-wrap")["answer"].startswith("chisel-wrap only calls chisel;")
    assert [c["verdict"]["why"] for c in wrapper["blocks"]["cards"]] == ["Wraps chisel", "Is called by chisel-wrap"]
    assert ask(client, "ponytail vs midway")["answer"].startswith(
        "ponytail and midway partly overlap; keep both only if you need the difference."
    )
    distinct = ask(client, "ponytail vs deck-maker")
    assert distinct["answer"].endswith("Same cluster: no") and "do different jobs." in distinct["answer"]


def test_usage_and_cost_edge_cases(client):
    reply = ask(client, "chisel-wrap vs stop-hook")
    rows = {r["label"]: r for r in reply["blocks"]["compare"]["rows"]}
    assert (rows["Every session"]["a"], rows["When used"]["a"]) == ("0 tokens", "5 tokens")
    assert rows["Usage"]["a"] == "Used 1 time in 30 days" and rows["Usage"]["b"] == "Usage unknown"
    assert rows["What it does"]["b"] == "No description."
    assert reply["blocks"]["compare"]["same_cluster"] is False


def test_usage_absent_everywhere(tmp_path, monkeypatch):
    data = {k: v for k, v in DATA.items() if k not in ("usage", "usage_window", "clusters", "overlaps", "costs")}
    reply = ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")
    rows = {r["label"]: r for r in reply["blocks"]["compare"]["rows"]}
    assert rows["Usage"] == {"label": "Usage", "a": "Usage unknown", "b": "Usage unknown"}
    assert rows["Every session"]["a"] == rows["Every session"]["b"] == "unknown"
    assert [c["verdict"]["label"] for c in reply["blocks"]["cards"]] == ["Not enough data"] * 2
    assert reply["blocks"]["cards"][0]["verdict"]["why"] == "Usage was not read in this scan"


def test_never_seen_without_a_window_span_and_empty_transcripts(tmp_path, monkeypatch):
    data = {**DATA, "usage_window": {"files": 2, "first": None, "last": None, "skipped": 0}}
    rows = ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")["blocks"]["compare"]["rows"]
    assert rows[-1]["b"] == "Not seen in past sessions" and rows[-1]["a"] == "Used 4 times, last used 30 Oct"
    data = {**DATA, "usage_window": {"files": 0, "first": None, "last": None, "skipped": 0}}
    assert ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")["blocks"]["compare"]["rows"][-1]["b"] == "Usage unknown"


def test_use_with_missing_last_date(tmp_path, monkeypatch):
    data = {**DATA, "usage": {"pt": {"count": 2, "last_used": None}}}
    assert ask(make(tmp_path, monkeypatch, data), "ponytail vs chisel")["blocks"]["compare"]["rows"][-1]["a"] == "Used 2 times in 30 days"


def test_missing_second_item_explains_the_first(client):
    reply = ask(client, "ponytail vs zzzqqq")
    assert reply["answer"].startswith('I could not find "zzzqqq" to compare with. Here is ponytail.\nponytail (skill)')
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt"]}] and names(reply) == ["ponytail"]


def test_unresolvable_first_item_or_same_item_twice(client):
    for question in ("zzzqqq vs ponytail", "ponytail vs ponytail", "how does it compare to ponytail"):
        reply = ask(client, question)
        assert reply["answer"].startswith("I could not tell which two Items you mean.") and reply["actions"] == []
        assert reply["blocks"]["next"] == "Name both Items, for example: compare ponytail to chisel."


def test_it_means_the_selected_item(client):
    reply = ask(client, "how does it compare to chisel", selected_ids=["pt"])
    assert names(reply) == ["ponytail", "chisel"]
    assert ask(client, "how does it compare to chisel", selected_ids=["ch"])["answer"].startswith("I could not tell")


def test_what_is_is_a_card_with_a_verdict(client):
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
                "ponytail (skill): Writes the smallest working diff.",
                "Every session: 1,200 tokens. When used: 3,000 tokens. Used 4 times in 30 days, last used 30 Oct.",
                "Duplicate with ponytail-copy.",
                "Keep one: Does the same job as ponytail-copy.",
                "Next: Open ponytail on the map to see what it connects to.",
            ]
        ), question
        assert reply["actions"] == [{"kind": "highlight", "item_ids": ["pt"]}]
    assert (
        ask(client, "wht is pony tail")["blocks"]["headline"].startswith('I took "pony tail"') is False
    )  # a strong match is not announced


def test_keep_and_remove_questions_lead_with_the_verdict(client):
    for question in ("Should I keep chisel?", "can i delete chisel", "get rid of chisel", "should i remove the chisel"):
        reply = ask(client, question)
        assert reply["blocks"]["headline"] == "chisel: Keep the wrapped one. Is called by chisel-wrap."
        assert reply["actions"] == [{"kind": "highlight", "item_ids": ["ch"]}]
    assert ask(client, "should I keep ponytail-copy")["blocks"]["headline"] == "ponytail-copy: Keep one. Does the same job as ponytail."
    assert ask(client, "should I keep chisel-wrap")["blocks"]["headline"] == "chisel-wrap: Keep the wrapped one. Wraps chisel."
    assert ask(client, "should I keep midway")["blocks"]["cards"][0]["verdict"] == {
        "label": "Not enough data",
        "tone": "unknown",
        "why": "Usage was not read for this Item",
    }
    assert ask(client, "should I keep it", selected_ids=["pt"])["blocks"]["cards"][0]["name"] == "ponytail"
    assert ask(client, "should I keep it")["blocks"]["headline"].startswith('I could not find "it"')


def test_verdict_from_usage_and_cost(tmp_path, monkeypatch):
    data = {
        **DATA,
        "overlaps": [],
        "costs": {"pt": {"always_on": 1200, "on_use": 1}},
        "usage": {"pt": {"count": 0, "last_used": None}, "ch": {"count": 3}},
    }
    client = make(tmp_path, monkeypatch, data)
    could_go = ask(client, "should I keep ponytail")["blocks"]["cards"][0]["verdict"]
    assert could_go == {
        "label": "Could go",
        "tone": "remove",
        "why": "Not seen in 30 days of past sessions and costs 1,200 tokens every session",
    }
    assert ask(client, "should I keep chisel")["blocks"]["cards"][0]["verdict"] == {
        "label": "Keep",
        "tone": "keep",
        "why": "Used 3 times in 30 days",
    }


def test_what_could_i_remove_lists_unused_items(client):
    reply = ask(client, "What could I remove?")
    assert "chisel" in [r["name"] for r in reply["blocks"]["rows"]] and "ch" in reply["actions"][0]["item_ids"]


def test_what_is_weak_or_missing(client):
    assert ask(client, "what is chsl")["blocks"]["headline"] == "Which one did you mean?"
    assert ask(client, "what is dckmkr")["blocks"]["headline"].startswith('I took "dckmkr" to mean deck-maker. ')
    reply = ask(client, "what is zzzqqq")
    assert reply["answer"] == 'I could not find "zzzqqq" in this scan.\nNext: Check the spelling, or describe what it does.'
    assert reply["blocks"]["follow_ups"][0] == "What do I have for zzzqqq?"
    assert reply["blocks"]["cards"] == [] and reply["actions"] == []


def test_meaning_finds_the_second_item_once_vectors_are_ready(client):
    for _ in range(100):  # vectors are built in a background thread
        reply = ask(client, "ponytail vs presentation")
        if "deck-maker" in names(reply):
            break
        time.sleep(0.05)
    assert "deck-maker" in names(reply) or reply["blocks"]["headline"] == "Which one did you mean?"


def test_answers_are_redacted_and_cached(client):
    first = ask(client, "what is ponytail")
    assert "sk-ant" not in str(first) and first["cached"] is False
    for _ in range(100):  # the first answers may predate the background vectors, which are part of the cache key
        if ask(client, "what is ponytail")["cached"]:
            break
        time.sleep(0.05)
    else:
        pytest.fail("never cached")
    assert "sk-ant" not in str(ask(client, "ponytail sk-ant-api03-abcdefghijklmnop vs chisel"))


def test_other_chat_questions_keep_their_routes(client):
    assert ask(client, "what is the total always-on cost?")["answer"].startswith("Before you type anything")
    assert ask(client, "what is this?", selected_ids=["pt"])["answer"].startswith("ponytail (skill)")
    assert ask(client, "how many items are there")["answer"] == "The current scan contains 7 Items."


def test_explain_with_a_cost_word_uses_the_selected_item(client):
    for question in ("Explain the cost", "Describe the tokens"):
        assert ask(client, question, selected_ids=["pt"])["answer"].startswith("ponytail (skill)")


def test_a_named_first_item_beats_the_selection(client):
    assert names(ask(client, "ponytail vs chisel", selected_ids=["ch"])) == ["ponytail", "chisel"]
    assert names(ask(client, "it vs chisel", selected_ids=["pt"])) == ["ponytail", "chisel"]


def test_a_typo_is_a_strong_match_and_only_a_weak_one_is_announced(client):
    assert ask(client, "ponytal vs dckmkr")["blocks"]["note"] == 'I took "dckmkr" to mean deck-maker.'  # a typo is a strong match


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
