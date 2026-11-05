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


# --- #55: session-start total --------------------------------------------------------------------------------------------------


def start_scan():
    items = [
        item("s1", "alpha"),
        item("s2", "beta"),
        item("s3", "gamma"),
        item("h1", "hook-one", "hook"),
        item("h2", "hook-two", "hook"),
        item("m", "mailbox", "mcp_server"),
        item("off", "sleeper", disabled=True),
        item("p", "pack", "plugin", disabled=True),
    ]
    return items, {
        "costs": {"s1": cost(500), "s2": cost(250), "s3": cost(None), "off": cost(9000)},
        "hook_weights": {"h1": {"bytes": 400, "tokens": 120}, "h2": {"bytes": 80, "tokens": None}},
        "memory_bytes": 2048,
    }


def test_session_start_total_equals_the_receipt_and_never_counts_unknown_as_zero(tmp_path, monkeypatch):
    items, extra = start_scan()
    client = make(tmp_path, monkeypatch, items, **extra)
    total = client.get("/api/lenses").json()["receipt"]["total_tokens"]
    assert total == 870  # 500 + 250 + 120; the disabled skill's 9000 is out
    for question in ("What do I pay before I type anything?", "What is the total always-on cost?", "session start cost"):
        blocks = ask(client, question)["blocks"]
        assert blocks["headline"] == f"Before you type anything, your setup loads about {total:,} tokens."
    blocks = ask(client, "What do I pay before I type anything?")["blocks"]
    assert [(r["name"], r["value"]) for r in blocks["rows"]] == [
        ("alpha", "500 tokens"),
        ("beta", "250 tokens"),
        ("hook-one", "120 tokens"),
        ("hook-two", "80 bytes, tokens not counted"),
    ]
    assert (
        blocks["note"] == "2 parts with no measured cost, not counted as 0. 2,128 bytes of hooks and CLAUDE.md not yet counted in tokens."
    )
    assert "sleeper" not in str(blocks) and "9,000" not in str(blocks)


def test_session_start_with_nothing_measured_says_so_not_zero(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, [item("s", "alpha"), item("m", "mailbox", "mcp_server")])
    blocks = ask(client, "what loads before I type anything")["blocks"]
    assert blocks["headline"] == "I cannot give a total: nothing that loads at session start has a measured cost."
    assert client.get("/api/lenses").json()["receipt"]["total_tokens"] is None
    assert "0" not in blocks["headline"]
    empty = make(tmp_path, monkeypatch, [item("n", "notes", "memory")])
    assert ask(empty, "session start total")["blocks"]["headline"] == "Nothing in this scan loads before your first prompt."


# --- #56: not used since N days ------------------------------------------------------------------------------------------------


def idle_scan(window=WINDOW):
    items = [
        item("a", "alpha"),
        item("b", "beta"),
        item("c", "gamma"),
        item("d", "delta"),
        item("e", "eps"),
        item("off", "sleeper", disabled=True),
    ]
    return items, {
        "costs": {"a": cost(100), "b": cost(300), "c": cost(50), "d": cost(900), "off": cost(700)},
        "usage": {
            "a": {"count": 2, "last_used": "2026-09-25"},  # 35 days before the newest session
            "b": {"count": 1, "last_used": "2026-08-30"},  # 61 days
            "c": {"count": 5, "last_used": "2026-10-28"},  # 2 days
            "d": NEVER,
            "e": {"count": 1, "last_used": "2026-09-01"},  # unknown cost, 59 days
            "off": NEVER,
        },
        "usage_window": window,
    }


def test_not_used_since_n_days_ranks_by_cost_and_states_the_lower_bound(tmp_path, monkeypatch):
    items, extra = idle_scan()
    client = make(tmp_path, monkeypatch, items, **extra)
    blocks = ask(client, "What have I not used in 30 days?")["blocks"]
    assert blocks["headline"] == "4 Items not used for 30 days or more, starting with delta."
    assert [(r["name"], r["value"]) for r in blocks["rows"]] == [
        ("delta", "At least 41 days idle; 900 tokens every session"),
        ("beta", "61 days idle; 300 tokens every session"),
        ("alpha", "35 days idle; 100 tokens every session"),
        ("eps", "59 days idle; Cost unknown"),
    ]
    assert "newest saved session" in blocks["note"] and "at least as long as the history" in blocks["note"]
    two_months = ask(client, "anything I haven't touched in 2 months?")["blocks"]
    # beta (61 days) only: the never-seen delta is idle 41+ days, which cannot prove 60
    assert two_months["headline"] == "1 Item not used for 60 days or more, starting with beta."
    assert ask(client, "what have I not used lately")["blocks"]["headline"].endswith("starting with delta.")
    nothing = ask(client, "what have I not used in 100 days")["blocks"]
    assert nothing["headline"] == "Nothing is recorded as unused for 100 days in 41 days of past sessions."


def test_short_history_cannot_prove_a_long_idle_span(tmp_path, monkeypatch):
    items, extra = idle_scan({"files": 2, "first": "2026-10-20", "last": "2026-10-30", "skipped": 0})
    extra["usage"].update({k: {"count": 1, "last_used": "2026-10-29"} for k in "be"})
    extra["usage"]["a"] = {"count": 2, "last_used": "2026-10-21"}
    blocks = ask(make(tmp_path, monkeypatch, items, **extra), "what have I not used in 30 days")["blocks"]
    assert blocks["headline"] == "Nothing is recorded as unused for 30 days in 11 days of past sessions."
    short = ask(make(tmp_path, monkeypatch, items, **extra), "what have I not used in 7 days")["blocks"]
    assert [r["value"] for r in short["rows"]][0] == "At least 11 days idle; 900 tokens every session"
    assert "alpha" in [r["name"] for r in short["rows"]]  # exactly 9 days idle


def test_not_used_needs_usage(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, [item("a", "alpha")])
    assert ask(client, "what have I not used in 30 days")["blocks"]["headline"] == "Usage was not read in this scan."
    client = make(
        tmp_path, monkeypatch, [item("a", "alpha")], usage={}, usage_window={"files": 0, "first": None, "last": None, "skipped": 0}
    )
    assert ask(client, "what have I not used in 30 days")["blocks"]["headline"] == "No transcripts found."


# --- #57: cost and usage by plugin ---------------------------------------------------------------------------------------------


def plugin_scan():
    items = [
        item("pk", "pdf-tools", "plugin"),
        item("p1", "pdf-read", origin="pdf-tools"),
        item("p2", "pdf-merge", "agent", origin="pdf-tools"),
        item("g1", "git-helper", origin="pat/skills"),
        item("g2", "git-log", origin="pat/skills"),
        item("g3", "git-misc", origin="pat/skills"),
        item("o1", "old-one", origin="retired", disabled=True),
        item("o2", "old-two", origin="retired", disabled=True),
        item("plain", "loner"),
    ]
    return items, {
        "costs": {
            "p1": cost(400),
            "p2": cost(100),
            "g1": cost(300),
            "g2": cost(200),
            "g3": cost(None),
            "o1": cost(5000),
            "plain": cost(10),
        },
        "usage": {
            "p1": {"count": 3, "last_used": "2026-10-29"},
            "p2": NEVER,
            "g1": NEVER,
            "g2": NEVER,
            "g3": NEVER,
            "o1": NEVER,
        },
        "usage_window": WINDOW,
    }


def test_plugin_roll_up_groups_by_origin_and_leaves_out_switched_off(tmp_path, monkeypatch):
    items, extra = plugin_scan()
    reply = ask(make(tmp_path, monkeypatch, items, **extra), "Which plugin is heaviest?")
    blocks = reply["blocks"]
    assert blocks["headline"] == "pat/skills is the heaviest: 500 tokens every session across 3 Items."  # tie on tokens: more unused first
    assert [(r["name"], r["value"], r["what"]) for r in blocks["rows"]] == [
        ("pat/skills", "500 tokens every session", "3 Items, 3 not seen, 1 cost unknown"),
        ("pdf-tools", "500 tokens every session", "2 Items, 1 not seen"),
    ]
    assert blocks["note"] == "Left out 1 switched-off plugin or pack: they cost nothing now."
    assert "retired" not in str([r["name"] for r in blocks["rows"]]) and "5,000" not in str(blocks)
    assert [r["id"] for r in blocks["rows"]] == ["g1", "pk"]  # the plugin Item when there is one, else its heaviest part
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["g1", "pk"]}]


def test_plugin_roll_up_without_origins_or_costs(tmp_path, monkeypatch):
    bare = make(tmp_path, monkeypatch, [item("a", "alpha")])
    assert ask(bare, "cost by plugin")["blocks"]["headline"] == "No Item in this scan has a known plugin or pack."
    blind = make(tmp_path, monkeypatch, [item("a", "alpha", origin="acme/tools")])
    blocks = ask(blind, "which plugin costs the most")["blocks"]
    assert blocks["headline"] == "Costs were not measured for any plugin or pack."
    assert blocks["rows"][0]["value"] == "Cost unknown"


# --- #58: refuse and hand off ---------------------------------------------------------------------------------------------------

REFUSE_SCAN = [item("pt", "pdf-tools", "plugin"), item("ts", "tune-spacing"), item("eh", "error-handler"), item("ud", "update-docs")]


def test_refusals_hand_off_a_copyable_instruction_and_change_nothing(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, REFUSE_SCAN)
    before = (tmp_path / "scan.json").read_bytes()
    cases = {
        "Disable the plugin pdf-tools": (
            "Constellation never changes your files. Claude Code can, and it asks you first.",
            "Disable the plugin pdf-tools. Show me every change before you make it and wait for my OK.",
        ),
        "please rename tune-spacing to tidy": (
            "Constellation never changes your files. Claude Code can, and it asks you first.",
            "please rename tune-spacing to tidy. Show me every change before you make it and wait for my OK.",
        ),
        "What does tune-spacing say in full?": (
            "Constellation does not read or show file contents. Claude Code can open the file for you.",
            'Open the file (the skill "tune-spacing") and tell me what it says, in full. Do not change anything.',
        ),
        "Why did my hook fail?": (
            "Constellation sees how your setup is shaped, not how it ran. Claude Code can look at the failure.",
            "Help me debug this: Why did my hook fail. Read the logs and my config, and change nothing until I agree.",
        ),
        "How do I write a new skill?": (
            "That is outside what this scan holds, so I would only guess. Claude Code is the better place to ask.",
            "How do I write a new skill",
        ),
    }
    for question, (headline, instruction) in cases.items():
        reply = ask(client, question)
        blocks = reply["blocks"]
        assert blocks["headline"] == headline, question
        assert blocks["handoff"] == {"instruction": instruction, "checklist_id": None}, question
        assert blocks["cards"] == [] and blocks["rows"] == [] and reply["actions"] == []
        assert reply["answer"].endswith(f"Ask Claude Code: {instruction}")
    assert (tmp_path / "scan.json").read_bytes() == before and not (tmp_path / "c.md").exists()


def test_item_names_that_look_like_commands_are_not_refused(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, REFUSE_SCAN)
    for question in ("what is error-handler", "what is update-docs", "Should I keep update-docs?", "why is pdf-tools so big"):
        assert ask(client, question)["blocks"]["handoff"] is None, question
    assert ask(client, "why is pdf-tools so big")["blocks"]["cards"][0]["name"] == "pdf-tools"
    for question in ("What do I pay before I type anything?", "How many items are there", "What could I remove?", "how do I use ponytail"):
        assert ask(client, question)["blocks"]["handoff"] is None, question
