"""Ask as a clean-up assistant, through POST /api/chat with invented Items: remove list, session start, idle days, plugins, hand-offs."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from constellation import server
from constellation.answer import DORMANT_DAYS

WINDOW = {"files": 9, "first": "2026-09-20", "last": "2026-10-30", "skipped": 0}  # 41 days
NEVER = {"count": 0, "last_used": None}


def item(id_, name, kind="skill", **extra):
    return {"id": id_, "name": name, "kind": kind, "description": f"{name} does a thing.", **extra}


def cost(n):
    return {"always_on": n, "on_use": None}


def make(tmp_path, monkeypatch, items, **extra):
    static = tmp_path / "static"
    static.mkdir(exist_ok=True)
    monkeypatch.setattr(server, "STATIC", static)
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"items": items, **extra}))
    app = server.create_app(path, checklist=tmp_path / "c.md", embedder=lambda texts: [[1.0] + [0.0] * 399 for _ in texts])
    return TestClient(app, base_url="http://127.0.0.1:8765")


def ask(client, question, **body):
    response = client.post("/api/chat", json={"question": question, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_dormant_days_matches_the_frontend_constant():
    source = (Path(__file__).parents[1] / "frontend/src/lib/verdict.ts").read_text()
    assert int(re.search(r"export const DORMANT_DAYS = (\d+)", source)[1]) == DORMANT_DAYS == 30


# --- #54: what could I remove ---------------------------------------------------------------------------------------------------


def removal_scan():
    items = [
        item("a", "alpha"),
        item("b", "beta"),
        item("d1", "dup-one"),
        item("d2", "dup-two"),
        item("w", "wrapper"),
        item("c", "core"),
        item("u", "mystery"),
        item("off", "sleeper", disabled=True),
        item("k", "kept"),
    ]
    return items, {
        "costs": {
            "a": cost(500),
            "b": cost(300),
            "d1": cost(200),
            "d2": cost(100),
            "w": cost(400),
            "c": cost(50),
            "off": cost(900),
            "k": cost(70),
        },
        "usage": {
            "a": NEVER,
            "b": NEVER,
            "u": NEVER,
            "w": NEVER,
            "off": NEVER,
            "d1": {"count": 3, "last_used": "2026-10-29"},
            "d2": {"count": 1, "last_used": "2026-10-20"},
            "c": {"count": 4, "last_used": "2026-10-29"},
            "k": {"count": 4, "last_used": "2026-10-29"},
        },
        "usage_window": WINDOW,
        "overlaps": [
            {"a_id": "d1", "b_id": "d2", "verdict": "duplicate", "reason": "Both do it."},
            {"a_id": "w", "b_id": "c", "verdict": "wrapper", "reason": "Calls core."},
        ],
    }


def test_remove_lists_removable_items_with_one_deduplicated_saving(tmp_path, monkeypatch):
    items, extra = removal_scan()
    reply = ask(make(tmp_path, monkeypatch, items, **extra), "What could I remove?")
    blocks = reply["blocks"]
    # alpha 500 + beta 300 + wrapper 400 (also listed as unused: counted once) + the cheaper duplicate dup-two 100; sleeper is disabled
    assert blocks["headline"] == "You could remove 5, saving about 1,300 tokens every session."
    assert [r["name"] for r in blocks["rows"]] == ["alpha", "wrapper", "beta", "dup-two", "mystery"]
    assert blocks["rows"][3]["value"] == "Same job as dup-one; saves 100 tokens"
    assert blocks["rows"][4]["value"] == "Not seen; saving unknown"
    assert blocks["note"].startswith("Plus 1 Item with an unknown saving, not counted as 0.")
    assert "sleeper" not in reply["answer"]
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["a", "w", "b", "d2", "u"]}]


def test_remove_with_nothing_to_remove_and_with_unknown_savings_only(tmp_path, monkeypatch):
    nothing = make(
        tmp_path,
        monkeypatch,
        [item("a", "alpha")],
        costs={"a": cost(5)},
        usage={"a": {"count": 2, "last_used": "2026-10-30"}},
        usage_window=WINDOW,
    )
    assert ask(nothing, "what can I get rid of")["blocks"]["headline"] == "Nothing in this scan looks safe to remove."
    blind = make(tmp_path, monkeypatch, [item("a", "alpha"), item("b", "beta")], usage={"a": NEVER, "b": NEVER}, usage_window=WINDOW)
    blocks = ask(blind, "clean up my setup")["blocks"]
    assert blocks["headline"] == "You could remove 2 Items, but the saving is unknown."
    assert "0 tokens" not in blocks["headline"]


def test_remove_shows_five_and_counts_the_rest(tmp_path, monkeypatch):
    items = [item(f"s{n}", f"skill-{n}") for n in range(7)]
    extra = {"costs": {f"s{n}": cost(10 * (n + 1)) for n in range(7)}, "usage": {f"s{n}": NEVER for n in range(7)}, "usage_window": WINDOW}
    blocks = ask(make(tmp_path, monkeypatch, items, **extra), "what could I remove")["blocks"]
    assert blocks["headline"] == "You could remove 7, saving about 280 tokens every session."
    assert len(blocks["rows"]) == 5 and blocks["more"] == 2


def test_could_go_needs_idle_days_and_cost(tmp_path, monkeypatch):
    short = {"files": 2, "first": "2026-10-20", "last": "2026-10-30", "skipped": 0}  # 11 days
    items = [item("a", "alpha"), item("b", "beta"), item("z", "zero")]
    costs = {"a": cost(100), "b": cost(100), "z": cost(0)}
    usage = {"a": NEVER, "b": {"count": 2, "last_used": "2026-09-25"}, "z": NEVER}  # b idle 35 days
    client = make(tmp_path, monkeypatch, items, costs=costs, usage=usage, usage_window=WINDOW)
    label = lambda name: ask(client, f"Should I keep {name}?")["blocks"]["cards"][0]["verdict"]  # noqa: E731
    assert label("alpha")["label"] == "Could go"
    assert label("beta") == {"label": "Review", "tone": "review", "why": "Idle 35 days; costs 100 tokens every session"}
    assert label("zero")["label"] == "Review"
    client = make(tmp_path, monkeypatch, items, costs=costs, usage=usage, usage_window=short)
    assert label("alpha")["label"] == "Review" and "history is short" in label("alpha")["why"]
