"""Answer blocks through POST /api/chat with invented Items: wording, limits, verdicts and the plain-text twin."""

import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.answer import to_text

WINDOW = {"files": 4, "first": "2026-10-01", "last": "2026-10-30", "skipped": 0}


AXES: dict[str, int] = {}


def apart(texts):
    """Every text gets its own axis, so nothing is similar in meaning to anything else."""
    return [[1.0 if AXES.setdefault(t, len(AXES)) == n else 0.0 for n in range(400)] for t in texts]


def make(tmp_path, monkeypatch, items, **extra):
    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    monkeypatch.setattr(server, "STATIC", static)
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"items": items, **extra}))
    app = server.create_app(path, checklist=tmp_path / "c.md", embedder=apart)
    return TestClient(app, base_url="http://127.0.0.1:8765")


def ask(client, question, **body):
    response = client.post("/api/chat", json={"question": question, **body})
    assert response.status_code == 200, response.text
    return response.json()


def item(id_, name, description="Does a thing.", kind="skill"):
    return {"id": id_, "name": name, "kind": kind, "description": description}


def what(tmp_path, monkeypatch, description, kind="skill"):
    client = make(tmp_path, monkeypatch, [item("p", "probe", description, kind)])
    return ask(client, "what is probe")["blocks"]["cards"][0]["what"]


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Plain words with no full stop", "Plain words with no full stop"),
        ("Reads files e.g. logs and more. Second one.", "Reads files e.g. logs and more."),
        ("Handles i.e. the case. Next.", "Handles i.e. the case."),
        ("Checks lint, tests etc. before a push. Next.", "Checks lint, tests etc. before a push."),
        ("Beats cat vs. dog. Tail.", "Beats cat vs. dog."),
        ("Ask J. Smith for help. Tail.", "Ask J. Smith for help."),
        ("See https://example.com/a.b/c for docs. More.", "See https://example.com/a.b/c for docs."),
        ("Is it fast? Yes. Tail.", "Is it fast?"),
        ("Wow! Tail.", "Wow!"),
        ("Use when the user says hello.", "Use when the user says hello."),
        ("Use when asked. Use this too. Use for x. Trigger on y. Invoke it. Draws a chart.", "Draws a chart."),
        ('Say "make a chart" to start. Draws charts.', "Draws charts."),
        ("Say “make a chart” to start. Draws charts.", "Draws charts."),
        ("Run /commit to save. Saves work.", "Saves work."),
        ("Reads /etc/hosts safely. Tail.", "Reads /etc/hosts safely."),
        ("trigger when idle. Waits.", "Waits."),
        ("# Title **bold** `code` [link text](http://x.y/z)", "Title bold code link text"),
        ("  Spaced \n\n out\ttext.  ", "Spaced out text."),
        ("", "No description."),
        ("   \n ", "No description."),
        ("...", "..."),
    ],
)
def test_first_sentence_rules(tmp_path, monkeypatch, description, expected):
    assert what(tmp_path, monkeypatch, description) == expected


def test_first_sentence_never_cuts_inside_a_word(tmp_path, monkeypatch):
    base = " ".join(["abcd"] * 24)  # 119 characters
    assert what(tmp_path, monkeypatch, base) == base
    assert what(tmp_path, monkeypatch, base + "x") == base + "x"  # 120
    assert what(tmp_path, monkeypatch, base + "xy") == " ".join(["abcd"] * 23) + "…"  # 121 drops the last word
    assert what(tmp_path, monkeypatch, "x" * 200) == "x" * 119 + "…"
    assert what(tmp_path, monkeypatch, "x" * 120) == "x" * 120
    assert what(tmp_path, monkeypatch, "x" * 121) == "x" * 119 + "…"
    assert what(tmp_path, monkeypatch, "word " * 60 + ". Tail.") == " ".join(["word"] * 24) + "…"


def test_kind_labels_are_plain(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, [item("m", "calendar", "Reads events.", "mcp_server"), item("h", "guard", "Guards.", "hook")])
    assert ask(client, "what is calendar")["blocks"]["cards"][0]["kind_label"] == "MCP server"
    assert ask(client, "what is guard")["blocks"]["cards"][0]["kind_label"] == "hook"
    assert ask(client, "what is guard")["answer"].startswith("guard (hook): Guards.")


@pytest.fixture
def client(tmp_path, monkeypatch):
    items = [
        item("a", "alpha-twin", "Writes release notes."),
        item("b", "beta-twin", "Writes release notes too."),
        item("w", "gamma-wrap", "Calls delta-core."),
        item("d", "delta-core", "Does the core work."),
        item("u", "epsilon-idle", "Sits unused."),
        item("s", "zeta-seen", "Is used a lot."),
        item("n", "eta-nodata", "No usage read."),
        item("z", "theta-free", "Costs nothing and is unused."),
        item("t", "iota-teapot", "Boils water."),
    ]
    return make(
        tmp_path,
        monkeypatch,
        items,
        costs={
            "a": {"always_on": 300, "on_use": None},
            "u": {"always_on": 1468, "on_use": 5210},
            "s": {"always_on": 10, "on_use": 20},
            "z": {"always_on": 0, "on_use": 0},
        },
        overlaps=[
            {"a_id": "a", "b_id": "b", "verdict": "duplicate", "reason": "Same job."},
            {"a_id": "w", "b_id": "d", "verdict": "wrapper", "reason": "Calls it."},
            {"a_id": "s", "b_id": "d", "verdict": "overlap", "reason": "Shares work."},
        ],
        usage={"u": {"count": 0}, "s": {"count": 12, "last_used": "2026-10-28T09:00:00Z"}, "z": {"count": 0}, "d": {"count": 1}},
        usage_window=WINDOW,
        clusters=[{"name": "notes", "item_ids": ["a", "b"]}],
    )


def verdict(client, name):
    return ask(client, f"should I keep {name}")["blocks"]["cards"][0]["verdict"]


def test_verdicts_come_only_from_local_signals(client):
    assert verdict(client, "alpha-twin") == {"label": "Keep one", "tone": "remove", "why": "Does the same job as beta-twin"}
    assert verdict(client, "beta-twin")["why"] == "Does the same job as alpha-twin"
    assert verdict(client, "gamma-wrap") == {"label": "Keep the wrapped one", "tone": "review", "why": "Wraps delta-core"}
    assert verdict(client, "delta-core") == {"label": "Keep the wrapped one", "tone": "review", "why": "Is called by gamma-wrap"}
    assert verdict(client, "epsilon-idle") == {
        "label": "Could go",
        "tone": "remove",
        "why": "Not seen in 30 days of past sessions and costs 1,468 tokens every session",
    }
    assert verdict(client, "zeta-seen") == {"label": "Keep", "tone": "keep", "why": "Used 12 times in 30 days"}
    assert verdict(client, "theta-free") == {"label": "Review", "tone": "review", "why": "Not seen in 30 days of past sessions"}
    assert verdict(client, "eta-nodata") == {"label": "Not enough data", "tone": "unknown", "why": "Usage was not read for this Item"}


def test_a_partial_overlap_does_not_decide_the_verdict(client):
    card = ask(client, "what is zeta-seen")["blocks"]["cards"][0]
    assert card["overlap"] == {"with_id": "d", "with_name": "delta-core", "verdict": "overlap", "reason": "Shares work."}
    assert card["verdict"]["label"] == "Keep"
    assert ask(client, "what is iota-teapot")["blocks"]["cards"][0]["overlap"] is None


def test_the_worst_overlap_is_shown_first(client):
    # delta-core has a wrapper and zeta-seen only overlaps it: the wrapper wins
    assert ask(client, "what is delta-core")["blocks"]["cards"][0]["overlap"]["verdict"] == "wrapper"


def test_no_usage_read_at_all(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, [item("a", "alpha")])
    card = ask(client, "should I keep alpha")["blocks"]["cards"][0]
    assert card["verdict"] == {"label": "Not enough data", "tone": "unknown", "why": "Usage was not read in this scan"}
    assert (card["always_on"], card["on_use"], card["usage"]) == ("unknown", "unknown", "Usage unknown")
    assert ask(client, "what have I never used")["answer"] == "Usage was not read in this scan."


def test_unknown_cost_is_never_zero_and_zero_is_shown(client):
    card = ask(client, "what is alpha-twin")["blocks"]["cards"][0]
    assert (card["always_on"], card["on_use"]) == ("300 tokens", "unknown")
    free = ask(client, "what is theta-free")["blocks"]["cards"][0]
    assert (free["always_on"], free["on_use"]) == ("0 tokens", "0 tokens")
    rows = ask(client, "what costs the most")["blocks"]["rows"]
    assert [r["value"] for r in rows] == [
        "1,468 tokens every session",
        "300 tokens every session",
        "10 tokens every session",
        "0 tokens every session",
    ]
    assert ask(client, "what costs the most")["blocks"]["note"] == "Plus 5 Items with unknown cost, not counted as 0."


def test_search_rows_say_cost_unknown(client):
    rows = ask(client, "boils water")["blocks"]["rows"]
    assert rows == [{"id": "t", "name": "iota-teapot", "kind": "skill", "what": "Boils water.", "value": "Cost unknown"}]
    assert ask(client, "boils water")["blocks"]["headline"] == "One Item matches: iota-teapot."


def test_usage_lines_and_dates(tmp_path, monkeypatch):
    usage = {
        "a": {"count": 1, "last_used": "2026-11-02T10:00:00Z"},
        "b": {"count": 2, "last_used": None},
        "c": {"count": 0},
    }
    client = make(
        tmp_path,
        monkeypatch,
        [item("a", "aa"), item("b", "bb"), item("c", "cc")],
        usage=usage,
        usage_window={**WINDOW, "last": "2026-10-01"},
    )
    lines = {n: ask(client, f"what is {n}")["blocks"]["cards"][0]["usage"] for n in ("aa", "bb", "cc")}
    assert lines == {"aa": "Used 1 time in 1 day, last used 2 Nov", "bb": "Used 2 times in 1 day", "cc": "Not seen in 1 day"}


def test_every_id_exists_and_every_limit_holds(client, tmp_path, monkeypatch):
    questions = [
        "what costs the most",
        "what have I never used",
        "show usage",
        "show duplicates",
        "what could I remove",
        "writes release notes",
        "explain these",
        "alpha-twin vs beta-twin",
        "should I keep alpha-twin",
        "what is nothing-here-qqzzyy",
        "how many items",
        "wxyz",
        "alpha-twin vs gamma",
    ]
    known = {"a", "b", "w", "d", "u", "s", "n", "z", "t"}
    for question in questions:
        reply = ask(client, question, selected_ids=["a", "b", "w"])
        b = reply["blocks"]
        assert len(b["headline"]) <= 140 and len(b["cards"]) <= 2 and len(b["rows"]) <= 5 and len(b["follow_ups"]) <= 3
        assert len(b["did_you_mean"]) <= 3 and all(len(c) <= 40 for c in b["follow_ups"])
        assert len(reply["answer"]) < 1200 and reply["answer"] == to_text(b) and reply["answer"].startswith(b["headline"])
        ids = {c["id"] for c in b["cards"]} | {r["id"] for r in b["rows"]} | {d["id"] for d in b["did_you_mean"]}
        ids |= {c["overlap"]["with_id"] for c in b["cards"] if c["overlap"]}
        assert ids <= known, question
        assert {i for a in reply["actions"] for i in a["item_ids"]} <= known
        assert "!" not in b["headline"]
        assert b["note"] is None or len(b["note"]) <= 160
        assert b["next"] is None or len(b["next"]) <= 100


def test_limits_cut_long_text_without_cutting_words(tmp_path, monkeypatch):
    names = [f"{'long-name-' * 12}{n}" for n in range(8)]
    items = [item(str(n), names[n], "Boils water. " + "extra " * 40) for n in range(8)]
    client = make(tmp_path, monkeypatch, items, costs={str(n): {"always_on": n * 1_000_000, "on_use": 0} for n in range(8)})
    reply = ask(client, "top costs")
    b = reply["blocks"]
    assert 130 < len(b["headline"]) <= 140 and b["headline"].endswith("…")
    assert len(b["rows"]) == 5 and b["more"] == 3 and b["follow_ups"] == ["What costs the most every session?", "What have I never used?"]
    assert "3 more. Ask a narrower question." in reply["answer"]
    assert len(reply["answer"]) <= 1200
    long = ask(client, "explain these", selected_ids=[str(n) for n in range(8)])
    assert len(long["blocks"]["cards"]) == 2 and len(long["blocks"]["rows"]) == 3 and long["blocks"]["more"] == 3
    assert len(long["answer"]) <= 1200


def test_the_plain_answer_is_cut_to_1200_characters(tmp_path, monkeypatch):
    items = [item(str(n), f"n{n}-" + "x" * 90, "y " * 70) for n in range(7)]
    client = make(tmp_path, monkeypatch, items)
    reply = ask(client, "explain these", selected_ids=[str(n) for n in range(7)])
    assert len(reply["answer"]) <= 1200 and reply["answer"] == to_text(reply["blocks"])


def test_did_you_mean_for_several_candidates_and_for_one(client):
    several = ask(client, "what is twn")
    assert several["blocks"]["headline"] == "Which one did you mean?" and several["blocks"]["cards"] == []
    assert [d["name"] for d in several["blocks"]["did_you_mean"]] == ["alpha-twin", "beta-twin"]
    assert [d["ask"] for d in several["blocks"]["did_you_mean"]] == ["What is alpha-twin?", "What is beta-twin?"]
    assert several["actions"] == [] and several["blocks"]["follow_ups"] == []
    keep = ask(client, "should I keep twn")["blocks"]["did_you_mean"]
    assert keep[0]["ask"] == "Should I keep alpha-twin?"
    one = ask(client, "what is tpt")["blocks"]
    assert one["headline"].startswith('I took "tpt" to mean iota-teapot. ') and one["did_you_mean"] == []
    assert len(one["headline"]) <= 140
    assert ask(client, "compare twn and zeta-seen")["blocks"]["did_you_mean"][0]["ask"] == "Compare alpha-twin and zeta-seen"
    assert ask(client, "compare zeta-seen and twn")["blocks"]["did_you_mean"][1]["ask"] == "Compare zeta-seen and beta-twin"


def test_not_found_never_lists_unrelated_items(client):
    for question in ("what is qqzzyy", "should I keep qqzzyy"):
        reply = ask(client, question)
        assert reply["answer"] == 'I could not find "qqzzyy" in this scan.\nNext: Check the spelling, or describe what it does.'
        assert reply["blocks"]["cards"] == [] and reply["blocks"]["rows"] == [] and reply["actions"] == []
        assert reply["blocks"]["follow_ups"] == [
            "What do I have for qqzzyy?",
            "What costs the most every session?",
            "What have I never used?",
        ]
    search = ask(client, "what do I have for flux capacitors")
    assert search["answer"] == 'I could not find "flux capacitors" in this scan.\nNext: Check the spelling, or describe what it does.'
    assert search["blocks"]["follow_ups"] == ["What costs the most every session?", "What have I never used?"]
    assert ask(client, "what do I have for boils")["blocks"]["rows"][0]["name"] == "iota-teapot"


def test_empty_lists_say_what_was_checked(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, [item("a", "aa")], usage={"a": {"count": 3}}, usage_window=WINDOW)
    reply = ask(client, "what have I never used")
    assert reply["answer"].startswith("Nothing here has been unused in 30 days of past sessions.\nBased on 4 saved transcripts.")
    assert ask(client, "show duplicates")["answer"] == "No known duplicates or wrappers in this scan."
    assert ask(client, "duplicates of aa")["answer"] == "No known duplicates or wrappers for those Items."
    assert ask(client, "what costs the most")["answer"].startswith("Token costs were not measured in this scan.")


def test_usage_without_transcripts(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, [item("a", "aa")], usage_window={**WINDOW, "files": 0})
    assert ask(client, "show usage")["answer"] == "No transcripts found."
    assert ask(client, "should I keep aa")["blocks"]["cards"][0]["verdict"]["why"] == "Usage was not read in this scan"


def test_pairs_and_unused_rows_beyond_five_say_how_many_more(tmp_path, monkeypatch):
    items = [item(f"x{n}", f"x-{n}") for n in range(7)] + [item("hub", "hub")]
    overlaps = [{"a_id": f"x{n}", "b_id": "hub", "verdict": "duplicate", "reason": "Same."} for n in range(7)]
    usage = {f"x{n}": {"count": 0} for n in range(7)}
    client = make(tmp_path, monkeypatch, items, overlaps=overlaps, usage=usage, usage_window=WINDOW)
    pairs = ask(client, "show duplicates")["blocks"]
    assert (len(pairs["rows"]), pairs["more"], pairs["headline"]) == (5, 2, "Found 7 duplicate or wrapper pairs, starting with x-0.")
    assert ask(client, "wrappers")["blocks"]["rows"][0]["value"] == "Does the same job as hub"
    unused = ask(client, "never used")["blocks"]
    assert (len(unused["rows"]), unused["more"]) == (5, 2) and unused[
        "headline"
    ] == "7 Items not seen in 30 days of past sessions, starting with x-0."
    assert unused["rows"][0]["value"] == "Cost unknown"


def test_a_single_pair_and_a_wrapper_row(tmp_path, monkeypatch):
    overlaps = [{"a_id": "w", "b_id": "c", "verdict": "wrapper", "reason": "Calls it."}]
    client = make(tmp_path, monkeypatch, [item("w", "wrap"), item("c", "core")], overlaps=overlaps)
    blocks = ask(client, "show wrappers")["blocks"]
    assert blocks["headline"] == "Found 1 duplicate or wrapper pair, starting with wrap."
    assert blocks["rows"][0]["value"] == "Wraps core" and blocks["more"] == 0


def test_starter_questions_are_answered(client):
    for question in (
        "Should I keep alpha-twin?",
        "What could I remove?",
        "What costs the most every session?",
        "What have I never used?",
        "What is alpha-twin?",
        "Compare alpha-twin and beta-twin",
        "What do I have for notes?",
    ):
        assert ask(client, question)["blocks"]["headline"], question
    compare = ask(client, "Compare alpha-twin and beta-twin")["blocks"]
    assert compare["headline"] == "alpha-twin and beta-twin do the same job; you could keep one."
    assert compare["compare"]["same_cluster"] is True and len(compare["cards"]) == 2


def test_hostile_text_is_redacted_everywhere_in_the_blocks(tmp_path, monkeypatch):
    secret = "sk-" + "Q" * 30
    items = [item("h", "hostile", f"Reads api_key=planted-value then {secret}. Tail."), item("g", "good", "Fine.")]
    overlaps = [{"a_id": "g", "b_id": "h", "verdict": "duplicate", "reason": f"Same as {secret}"}]
    client = make(tmp_path, monkeypatch, items, overlaps=overlaps, clusters=[{"name": f"group {secret}", "item_ids": ["g", "h"]}])
    for question in (f"what is hostile {secret}", "should I keep hostile", "hostile vs good", "show duplicates", "what is good"):
        text = json.dumps(ask(client, question))
        assert secret not in text and "planted-value" not in text, question
    assert "[REDACTED]" in ask(client, "what is hostile")["blocks"]["cards"][0]["what"]
    assert ask(client, "what is hostile")["blocks"]["cards"][0]["overlap"]["reason"] == "Same as [REDACTED]"
    assert re.fullmatch(r"[a-z]", ask(client, "what is good")["blocks"]["cards"][0]["id"])  # ids are never rewritten


def test_blocks_are_cached_with_the_answer(client):
    first = ask(client, "what is alpha-twin")
    for _ in range(100):  # the background vectors are part of the cache key
        second = ask(client, "what is alpha-twin")
        if second["cached"]:
            break
        time.sleep(0.05)
    assert second == {**first, "cached": True}
    assert first["blocks"]["follow_ups"][0] == "Should I keep alpha-twin?"


def test_cut_boundaries():
    from constellation.answer import cut

    assert cut(" " + "x" * 200, 120) == " " + "x" * 118 + "…"
    assert cut("a " + "x" * 200, 120) == "a…"
    assert cut("aaa  " + "x" * 200, 120) == "aaa…"
    assert cut("ab cd", 5) == "ab cd"


def test_no_span_wording_and_overlap_priority(tmp_path, monkeypatch):
    items = [item("a", "alpha"), item("z", "zulu"), item("y", "yankee"), item("c", "custom", kind="custom_thing"), item("i", "idle")]
    overlaps = [
        {"a_id": "a", "b_id": "y", "verdict": "wrapper", "reason": "Calls it."},
        {"a_id": "z", "b_id": "a", "verdict": "duplicate", "reason": "Same."},
        {"a_id": "y", "b_id": "a", "verdict": "overlap", "reason": "Some."},
    ]
    window = {"files": 2, "first": None, "last": None, "skipped": 0}
    client = make(
        tmp_path,
        monkeypatch,
        items,
        overlaps=overlaps,
        usage={"i": {"count": 0}},
        usage_window=window,
        costs={"i": {"always_on": 5, "on_use": 0}},
    )
    card = ask(client, "what is alpha")["blocks"]["cards"][0]
    assert card["overlap"]["verdict"] == "duplicate" and card["overlap"]["with_id"] == "z"
    assert ask(client, "what is zulu")["blocks"]["cards"][0]["overlap"]["with_id"] == "a"
    assert ask(client, "what is custom")["blocks"]["cards"][0]["kind_label"] == "custom thing"
    why = ask(client, "should I keep idle")["blocks"]["cards"][0]["verdict"]["why"]
    assert why == "Not seen in the saved past sessions and costs 5 tokens every session"
    assert ask(client, "never used")["blocks"]["headline"] == "1 Item not seen in the saved past sessions, starting with idle."


def test_chip_length_boundary_and_candidate_cap(tmp_path, monkeypatch):
    items = [
        item("a", "a" * 24),
        item("b", "b" * 25),
        item("c", "c" * 26),
        item("t1", "one-twin"),
        item("t2", "two-twin"),
        item("t3", "three-twin"),
        item("t4", "four-twin"),
    ]
    client = make(tmp_path, monkeypatch, items)
    assert ask(client, f"what is {'a' * 24}")["blocks"]["follow_ups"][0] == f"Should I keep {'a' * 24}?"  # 39 characters
    assert ask(client, f"what is {'b' * 25}")["blocks"]["follow_ups"][0] == f"Should I keep {'b' * 25}?"  # exactly 40 fits
    assert ask(client, f"what is {'c' * 26}")["blocks"]["follow_ups"][0] == "What costs the most every session?"  # 41 is dropped
    assert len(ask(client, "what is twn")["blocks"]["did_you_mean"]) == 3


def test_follow_ups_for_every_answer_kind(tmp_path, monkeypatch):
    ask_next = ["What costs the most every session?", "What have I never used?"]
    client = make(
        tmp_path,
        monkeypatch,
        [item("a", "aa"), item("b", "bb")],
        usage={"a": {"count": 3}, "b": {"count": 3}},
        usage_window=WINDOW,
        overlaps=[{"a_id": "a", "b_id": "b", "verdict": "duplicate", "reason": "Same."}],
        costs={"a": {"always_on": 1, "on_use": 1}, "b": {"always_on": 2, "on_use": 1}},
    )
    follow = lambda q, **kw: ask(client, q, **kw)["blocks"]["follow_ups"]  # noqa: E731
    assert follow("how many items") == ask_next
    assert follow("what have I never used") == ask_next
    assert follow("show usage") == ask_next
    assert follow("what costs the most") == ["Should I keep bb?", *ask_next]
    assert follow("show duplicates") == ["Should I keep aa?", *ask_next]
    assert follow("what is aa") == ["Should I keep aa?", *ask_next]
    assert follow("should I keep aa") == ["What is aa?", *ask_next]
    assert follow("should I keep this", selected_ids=["b"]) == ["What is bb?", *ask_next]
    assert follow("should I keep that", selected_ids=["b"]) == ["What is bb?", *ask_next]
    assert follow("aa vs aa") == ask_next
    assert follow("aa vs qqzzyy") == ["Should I keep aa?"]
    assert ask(client, "aa vs qqzzyy")["blocks"]["next"] == "Check the spelling of the second name."
    assert follow("search mystery word") == ask_next
    no_cost = make(tmp_path / "n", monkeypatch, [item("a", "aa")]) if (tmp_path / "n").mkdir() is None else None
    reply = ask(no_cost, "what costs the most")["blocks"]
    assert reply["follow_ups"] == ask_next and reply["note"] == "Plus 1 Item with unknown cost, not counted as 0."
    assert ask(client, "what costs the most")["blocks"]["note"] is None
    assert ask(no_cost, "show duplicates")["blocks"]["follow_ups"] == ask_next
    assert ask(no_cost, "what is aa")["blocks"]["follow_ups"][0] == "Should I keep aa?"
    assert ask(client, "find bb")["blocks"]["follow_ups"] == ["Should I keep bb?", *ask_next]
    idle = (
        make(tmp_path / "i", monkeypatch, [item("a", "aa")], usage={"a": {"count": 0}}, usage_window=WINDOW)
        if (tmp_path / "i").mkdir() is None
        else None
    )
    assert ask(idle, "what have I never used")["blocks"]["follow_ups"] == ["Should I keep aa?", *ask_next]
    assert ask(idle, "show usage")["blocks"]["follow_ups"] == ask_next


def test_search_with_long_or_wordless_questions_names_the_terms(client):
    long = "xqz " * 15
    assert ask(client, long)["blocks"]["headline"] == f'I could not find "{("xqz " * 15)[:40]}" in this scan.'
    stop = "what can help me to do a an the with for please find search show"
    assert ask(client, stop)["blocks"]["headline"] == f'I could not find "{stop[:40]}" in this scan.'


def test_pronouns_and_both_weak_names(client):
    assert ask(client, "should I keep this", selected_ids=["a"])["blocks"]["cards"][0]["id"] == "a"
    assert ask(client, "should I keep that", selected_ids=["a"])["blocks"]["cards"][0]["id"] == "a"
    assert ask(client, "should I keep it")["blocks"]["headline"] == 'I could not find "it" in this scan.'
    note = ask(client, "tpt vs ztsn")["blocks"]["note"]
    assert note == 'I took "tpt" to mean iota-teapot and "ztsn" to mean zeta-seen.'


def test_ids_are_never_rewritten_by_redaction(tmp_path, monkeypatch):
    odd = "sk-" + "A" * 30
    client = make(tmp_path, monkeypatch, [item(odd, "oddity", "Fine.")])
    assert ask(client, "what is oddity")["blocks"]["cards"][0]["id"] == odd


def test_a_named_item_beats_the_selection_in_any_case(client):
    reply = ask(client, "EXPLAIN Epsilon-Idle", selected_ids=["a"])
    assert [c["id"] for c in reply["blocks"]["cards"]] == ["u"] and reply["blocks"]["rows"] == []


def test_overlap_ids_are_never_rewritten_by_redaction(tmp_path, monkeypatch):
    one, two = "sk-" + "A" * 30, "sk-" + "B" * 30
    overlaps = [{"a_id": one, "b_id": two, "verdict": "duplicate", "reason": "Same."}]
    client = make(tmp_path, monkeypatch, [item(one, "first-odd"), item(two, "second-odd")], overlaps=overlaps)
    assert ask(client, "what is first-odd")["blocks"]["cards"][0]["overlap"]["with_id"] == two
