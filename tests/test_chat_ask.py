"""Ask as a clean-up assistant, through POST /api/chat with invented Items: remove list, session start, idle days, plugins, hand-offs."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constellation import server

WINDOW = {"files": 60, "first": "2026-09-20", "last": "2026-10-30", "skipped": 0}  # 41 days, 60 sessions: enough for NEED.high
NEVER = {"count": 0, "last_used": None}


def item(id_, name, kind="skill", **extra):
    return {
        "id": id_,
        "name": name,
        "kind": kind,
        "description": f"{name} does one particular thing for the people who use this setup.",
        **extra,
    }


def cost(n):
    return {"always_on": n, "on_use": None}


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


def test_the_frontend_reader_defines_no_day_threshold():
    path = Path(__file__).parents[1] / "frontend/src/lib/verdict.ts"
    if not path.exists():  # mutmut runs tests from a copy without the frontend
        pytest.skip("frontend sources are not in this checkout")
    source = path.read_text()
    assert not re.search(r"const\s+\w*DAYS\w*\s*=\s*\d", source)  # verdict.py decides; verdict.ts only maps tiers to words


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
    # alpha 500 + beta 300 + wrapper 400; dup-two is used too (Review, not removable), mystery has no cost, sleeper is disabled
    assert blocks["headline"] == "You could remove 3, saving about 1,200 tokens every session."
    assert [r["name"] for r in blocks["rows"]] == ["wrapper", "alpha", "beta"]
    assert blocks["rows"][0]["value"] == "Only calls core; saves 400 tokens"
    assert blocks["rows"][1]["value"] == "Not seen; saves 500 tokens"
    assert not blocks["note"].startswith("Plus")
    assert "sleeper" not in reply["answer"]
    assert reply["actions"] == [{"kind": "highlight", "item_ids": ["w", "a", "b"]}]


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
    uncosted = make(tmp_path, monkeypatch, [item("a", "alpha"), item("b", "beta")], usage={"a": NEVER, "b": NEVER}, usage_window=WINDOW)
    assert ask(uncosted, "clean up my setup")["blocks"]["headline"] == "Nothing in this scan looks safe to remove."  # no cost, no reason
    blind = make(
        tmp_path,
        monkeypatch,
        [item("a", "alpha"), item("b", "beta")],
        usage={"a": NEVER, "b": NEVER},
        usage_window=WINDOW,
        overlaps=[{"a_id": "a", "b_id": "b", "verdict": "wrapper", "reason": "Calls it."}],
    )
    blocks = ask(blind, "clean up my setup")["blocks"]
    assert blocks["headline"] == "You could remove 1 Item, but the saving is unknown."
    assert "0 tokens" not in blocks["headline"]


def test_remove_shows_five_and_counts_the_rest(tmp_path, monkeypatch):
    items = [item(f"s{n}", f"skill-{n}") for n in range(7)]
    extra = {"costs": {f"s{n}": cost(100 * (n + 1)) for n in range(7)}, "usage": {f"s{n}": NEVER for n in range(7)}, "usage_window": WINDOW}
    blocks = ask(make(tmp_path, monkeypatch, items, **extra), "what could I remove")["blocks"]
    assert blocks["headline"] == "You could remove 7, saving about 2,800 tokens every session."
    assert len(blocks["rows"]) == 5 and blocks["more"] == 2


def test_could_go_needs_idle_days_and_cost(tmp_path, monkeypatch):
    short = {"files": 2, "first": "2026-10-20", "last": "2026-10-30", "skipped": 0}  # 11 days
    items = [item("a", "alpha"), item("b", "beta"), item("z", "zero")]
    costs = {"a": cost(100), "b": cost(100), "z": cost(0)}
    usage = {"a": NEVER, "b": {"count": 2, "last_used": "2026-09-25"}, "z": NEVER}  # b idle 35 days
    client = make(tmp_path, monkeypatch, items, costs=costs, usage=usage, usage_window=WINDOW)
    label = lambda name: ask(client, f"Should I keep {name}?")["blocks"]["cards"][0]["verdict"]  # noqa: E731
    assert label("alpha")["label"] == "Could go"
    assert label("beta") == {"label": "Review", "tone": "review", "why": "Not used in 35 active days"}
    assert label("zero")["label"] == "Review"
    client = make(tmp_path, monkeypatch, items, costs=costs, usage=usage, usage_window=short)
    assert label("alpha")["label"] == "Not enough history yet"


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


# --- #53: hand-off on every verdict ---------------------------------------------------------------------------------------------


def handoff_scan():
    items = [item(f"s{n}", f"skill-{n}") for n in range(6)] + [
        item("pk", "pdf-tools", "plugin"),
        item("mc", "mailbox", "mcp_server"),
        item("ag", "scribe", "agent", origin="acme/tools"),
        item("t1", "twin-one"),
        item("t2", "twin-two"),
        item("w", "shim"),
        item("c", "core"),
        item("geo", "geo-helper"),
        item("hk", "pre-hook", "hook"),
    ]
    costs = {f"s{n}": cost(100 * (n + 1)) for n in range(6)}  # s5 is the dearest; s0 falls outside the top five
    costs.update({"mc": cost(40), "ag": cost(30), "t1": cost(20), "t2": cost(10), "w": cost(5), "c": cost(5)})
    return items, {
        "costs": costs,
        "usage": {
            **{f"s{n}": NEVER for n in range(6)},
            "mc": NEVER,
            "ag": {"count": 3, "last_used": "2026-10-29"},
            "geo": {"count": 6, "last_used": "2026-10-29"},
        },
        "usage_window": WINDOW,
        "usage_by_project": {"geo": {"projectkey1": {"count": 6, "last_used": "2026-10-29"}}},
        "projects": {"projectkey1": "my-private-project"},
        "overlaps": [
            {"a_id": "t1", "b_id": "t2", "verdict": "duplicate", "reason": "Same."},
            {"a_id": "w", "b_id": "c", "verdict": "wrapper", "reason": "Calls."},
        ],
    }


def card_handoff(client, name):
    card = ask(client, f"What is {name}?")["blocks"]["cards"][0]
    return card["handoff"]


def test_every_card_ends_in_a_per_kind_instruction(tmp_path, monkeypatch):
    items, extra = handoff_scan()
    client = make(tmp_path, monkeypatch, items, **extra)
    said = {
        name: card_handoff(client, name)["instruction"]
        for name in ("skill-5", "pdf-tools", "mailbox", "scribe", "twin-one", "shim", "core", "geo-helper")
    }
    confirm = " Show me exactly what will change and wait for my OK."
    assert said["skill-5"] == 'Remove the skill "skill-5": find its folder (under ~/.claude/skills) and delete only that folder.' + confirm
    review = "tell me what it does and whether I still need it. Change nothing."
    assert said["pdf-tools"] == f'Review the plugin "pdf-tools": {review}'  # a plugin with no verdict to act on
    assert said["mailbox"] == f'Review the MCP server "mailbox": {review}'  # costs too little to be worth removing
    assert (
        said["twin-one"]
        == 'Remove the skill "twin-one": find its folder (under ~/.claude/skills) and delete only that folder. '
        + 'It does the same job as "twin-two", which stays.'
        + confirm
    )
    assert said["shim"] == 'The skill "shim" only calls "core". Show me how to use "core" directly, then remove "shim".' + confirm
    assert said["core"] == f'Review the skill "core": {review}'
    assert said["geo-helper"].startswith('Move the skill "geo-helper" out of my global setup')
    assert said["scribe"] == 'Review the agent "scribe": tell me what it does and whether I still need it. Change nothing.'
    assert "my-private-project" not in str(ask(client, "What is geo-helper?"))


def test_origin_is_named_so_a_plugins_files_are_not_edited_in_place(tmp_path, monkeypatch):
    items, extra = handoff_scan()
    extra["usage"]["ag"] = NEVER
    extra["costs"]["ag"] = cost(300)
    text = card_handoff(make(tmp_path, monkeypatch, items, **extra), "scribe")["instruction"]
    assert (
        text.startswith('Remove the agent "scribe"') and 'It came from "acme/tools": if that is a plugin or pack, change it there' in text
    )


def test_checklist_ids_are_exactly_the_rows_the_checklist_accepts(tmp_path, monkeypatch):
    items, extra = handoff_scan()
    client = make(tmp_path, monkeypatch, items, **extra)
    summary = client.get("/api/brief").json()
    rows = summary["safe"]["rows"] + summary["look"]["rows"]
    addable = {r["item_ids"][0]: r["id"] for r in rows}
    ids = {
        name: card_handoff(client, name)["checklist_id"]
        for name in ("skill-5", "skill-4", "skill-0", "twin-one", "geo-helper", "pdf-tools")
    }
    assert ids["skill-5"] == addable["s5"] and ids["skill-4"] == addable["s4"] and ids["skill-0"] == addable["s0"]
    assert ids["pdf-tools"] is None  # a wait row is not addable
    move = next(r for r in rows if r["kind"] == "move_to_project")
    assert ids["geo-helper"] == move["id"] and "my-private-project" not in str(summary["look"]["rows"][0])
    pair = next(r for r in rows if r["item_ids"] == ["t1", "t2"])
    assert ids["twin-one"] == pair["id"]
    for name in ("skill-5", "twin-one"):
        row_id = ids[name]
        first = client.post("/api/checklist", json={"id": row_id})
        assert first.status_code == 200 and first.json()["added"] is True and row_id in first.json()["ids"]
        assert client.post("/api/checklist", json={"id": row_id}).json()["added"] is False
    assert client.post("/api/checklist", json={"id": "feedfeedfeed"}).status_code == 404


def test_the_remove_list_ends_in_one_instruction_for_its_rows(tmp_path, monkeypatch):
    items, extra = handoff_scan()
    blocks = ask(make(tmp_path, monkeypatch, items, **extra), "what could I remove")["blocks"]
    hand = blocks["handoff"]
    assert hand["checklist_id"] is None
    assert hand["instruction"].startswith('Review these in my Claude Code setup as removal candidates: skill "skill-5", ')
    assert hand["instruction"].endswith("Show me each one and wait for my OK before you remove anything.")


# --- exact fields, boundaries and wording (mutation kills) ---------------------------------------------------------------------

FOLLOW = ["What costs the most every session?", "What have I never used?"]


def sk(n, prefix="skill"):
    return item(f"{prefix}{n}", f"{prefix}-{n}")


def unused(items, costs=None):
    return {"usage": {i["id"]: NEVER for i in items}, "usage_window": WINDOW, "costs": costs or {}}


def test_remove_exact_fields_and_row_limits(tmp_path, monkeypatch):
    items, extra = removal_scan()
    reply = ask(make(tmp_path, monkeypatch, items, **extra), "What could I remove?")
    blocks = reply["blocks"]
    assert blocks["next"] == "Open one on the map before you decide."
    assert blocks["follow_ups"] == ["Should I keep wrapper?", *FOLLOW]
    assert blocks["more"] == 0
    assert blocks["note"] == "Unused rests on saved transcripts, which Claude Code deletes over time."
    for count, more in ((5, 0), (6, 1)):
        many = [sk(n) for n in range(count)]
        costs = {i["id"]: cost(1500) for i in many}
        reply = ask(make(tmp_path, monkeypatch, many, **unused(many, costs)), "what could I remove")
        assert len(reply["blocks"]["rows"]) == 5 and reply["blocks"]["more"] == more
        assert len(reply["actions"][0]["item_ids"]) == 5
        assert reply["blocks"]["rows"][0]["value"] == "Not seen; saves 1,500 tokens"
        assert reply["blocks"]["note"] == "Unused rests on saved transcripts, which Claude Code deletes over time."
        assert len(reply["blocks"]["handoff"]["instruction"].split('skill "')) == 6  # five names
    empty = ask(make(tmp_path, monkeypatch, [item("a", "alpha")]), "what could I remove")["blocks"]
    assert empty["follow_ups"] == FOLLOW and empty["handoff"] is None


def test_remove_wrapper_and_unknown_duplicate_rows(tmp_path, monkeypatch):
    items = [item("w", "shim"), item("c", "core")]
    extra = {
        "costs": {"w": cost(40), "c": cost(5)},
        "usage": {"w": NEVER, "c": {"count": 2, "last_used": "2026-10-29"}},
        "usage_window": WINDOW,
        "overlaps": [{"a_id": "w", "b_id": "c", "verdict": "wrapper", "reason": "Calls."}],
    }
    blocks = ask(make(tmp_path, monkeypatch, items, **extra), "what could I remove")["blocks"]
    assert blocks["headline"] == "You could remove 1, saving about 40 tokens every session."
    assert blocks["rows"][0]["value"] == "Only calls core; saves 40 tokens"
    pair = [item("d1", "dup-one"), item("d2", "dup-two")]
    extra = {"overlaps": [{"a_id": "d1", "b_id": "d2", "verdict": "duplicate", "reason": "Same."}]}
    reply = ask(make(tmp_path, monkeypatch, pair, **extra), "what could I remove")
    assert reply["blocks"]["rows"][0]["name"] == "dup-one" and reply["blocks"]["follow_ups"][0] == "Should I keep dup-one?"
    assert reply["blocks"]["rows"][0]["value"] == "Same job as dup-two; saving unknown"
    assert reply["actions"][0]["item_ids"] == ["d1"] and 'skill "dup-one"' in reply["blocks"]["handoff"]["instruction"]
    costed = {"costs": {"d1": cost(200), "d2": cost(100)}, **extra}
    reply = ask(make(tmp_path, monkeypatch, pair, **costed), "what could I remove")
    assert reply["blocks"]["rows"][0]["name"] == "dup-one" and reply["blocks"]["follow_ups"][0] == "Should I keep dup-one?"  # dearer goes


def test_start_exact_fields_and_limits(tmp_path, monkeypatch):
    for count, more in ((5, 0), (6, 1)):
        many = [sk(n) for n in range(count)]
        costs = {i["id"]: cost(100 + n) for n, i in enumerate(many)}
        reply = ask(make(tmp_path, monkeypatch, many, costs=costs), "what do I pay before I type anything")
        blocks = reply["blocks"]
        assert len(blocks["rows"]) == 5 and blocks["more"] == more and len(reply["actions"][0]["item_ids"]) == 5
        assert blocks["next"] == f"Check whether you still use skill-{count - 1}." and blocks["follow_ups"] == FOLLOW
        assert blocks["note"] is None
    mixed = [item("h1", "hook-one", "hook"), item("s", "alpha")]
    reply = ask(
        make(tmp_path, monkeypatch, mixed, costs={"s": cost(5)}, hook_weights={"h1": {"bytes": 9, "tokens": None}}), "session start total"
    )
    assert reply["blocks"]["rows"][0]["name"] == "alpha" and reply["blocks"]["next"] == "Check whether you still use alpha."
    only_bytes = make(tmp_path, monkeypatch, mixed[:1], hook_weights={"h1": {"bytes": 9, "tokens": None}})
    assert ask(only_bytes, "session start total")["blocks"]["next"] is None
    heavy_bytes = [item("h1", "hook-one", "hook"), item("h2", "hook-two", "hook"), item("s", "alpha")]
    weights = {"h1": {"bytes": 9, "tokens": None}, "h2": {"bytes": 7, "tokens": None}}
    second = make(tmp_path, monkeypatch, heavy_bytes, costs={"s": cost(5)}, hook_weights=weights)
    assert ask(second, "session start total")["blocks"]["next"] == "Check whether you still use alpha."
    two = [item("s1", "alpha"), item("s2", "beta")]
    zero = ask(make(tmp_path, monkeypatch, two, costs={"s1": cost(0), "s2": cost(0)}), "session start total")["blocks"]
    assert zero["next"] is None and zero["headline"] == "Before you type anything, your setup loads about 0 tokens."
    first_bytes = [item("h1", "hook-one", "hook"), item("s", "alpha"), item("t", "beta")]
    third = make(tmp_path, monkeypatch, first_bytes, costs={"s": cost(0), "t": cost(5)}, hook_weights={"h1": {"bytes": 9, "tokens": None}})
    assert ask(third, "session start total")["blocks"]["next"] == "Check whether you still use beta."
    empty = ask(make(tmp_path, monkeypatch, [item("n", "notes", "memory")]), "session start total")["blocks"]
    assert empty["follow_ups"] == FOLLOW


def test_hook_weights_that_are_not_objects_are_ignored(tmp_path, monkeypatch):
    items = [item("h", "hook-one", "hook"), item("s", "alpha")]
    client = make(tmp_path, monkeypatch, items, costs={"s": cost(7)}, hook_weights={"h": "junk", "ghost": {"bytes": 1, "tokens": 999}})
    assert ask(client, "session start total")["blocks"]["headline"] == "Before you type anything, your setup loads about 7 tokens."


def plugin_groups(count):
    items, costs = [], {}
    for n in range(count):
        member = item(f"m{n}", f"part-{n}", origin=f"pack-{n}")
        items.append(member)
        costs[member["id"]] = cost(100 * (n + 1))
    return items, {"costs": costs}


def test_plugin_roll_up_exact_fields_ordering_and_limits(tmp_path, monkeypatch):
    for count, more in ((5, 0), (6, 1)):
        items, extra = plugin_groups(count)
        reply = ask(make(tmp_path, monkeypatch, items, **extra), "cost by plugin")
        blocks = reply["blocks"]
        assert len(blocks["rows"]) == 5 and blocks["more"] == more and len(reply["actions"][0]["item_ids"]) == 5
        assert blocks["follow_ups"] == FOLLOW and blocks["note"] is None
        assert blocks["next"] == f"One decision on pack-{count - 1} could replace many."
        assert blocks["rows"][0]["kind"] == "plugin" and blocks["rows"][0]["value"] == f"{100 * count:,} tokens every session"
        assert [r["name"] for r in blocks["rows"]][:2] == [f"pack-{count - 1}", f"pack-{count - 2}"]  # most expensive first
    none = ask(make(tmp_path, monkeypatch, [item("a", "alpha")]), "cost by plugin")["blocks"]
    assert none["follow_ups"] == FOLLOW


def test_plugin_roll_up_unknown_last_ties_zero_and_the_heaviest_part(tmp_path, monkeypatch):
    items = [
        item("a1", "a-blind", origin="aaa-blind"),
        item("b1", "b-zero-one", origin="bbb-zero"),
        item("b2", "b-zero-two", origin="bbb-zero"),
        item("c1", "c-one", origin="ccc-one"),
        item("d1", "d-light", origin="ddd-mixed"),
        item("d2", "d-heavy", origin="ddd-mixed"),
        item("d3", "d-blind", origin="ddd-mixed"),
        item("pk", "ddd-mixed", "plugin", origin="ddd-mixed"),
        item("z1", "z-off-one", origin="off-one", disabled=True),
        item("z2", "z-off-two", origin="off-two", disabled=True),
    ]
    costs = {"b1": cost(0), "b2": cost(0), "c1": cost(1), "d1": cost(10), "d2": cost(20), "z1": cost(9)}
    usage = {"b1": NEVER, "b2": NEVER, "c1": {"count": 1, "last_used": "2026-10-29"}}
    reply = ask(make(tmp_path, monkeypatch, items, costs=costs, usage=usage, usage_window=WINDOW), "which plugin costs the most")
    rows = reply["blocks"]["rows"]
    assert [(r["name"], r["value"]) for r in rows] == [
        ("ddd-mixed", "30 tokens every session"),
        ("ccc-one", "1 tokens every session"),
        ("bbb-zero", "0 tokens every session"),
        ("aaa-blind", "Cost unknown"),
    ]
    assert rows[3]["id"] == "a1" and rows[0]["id"] == "pk"
    assert rows[0]["what"] == "3 Items, 0 not seen, 1 cost unknown"
    assert reply["blocks"]["note"] == "Left out 2 switched-off plugin or packs: they cost nothing now."
    solo = [item("m", "part", origin="acme/x"), item("p", "other", origin="acme/x"), item("q", "third", origin="acme/x")]
    heaviest = ask(make(tmp_path, monkeypatch, solo, costs={"m": cost(1), "p": cost(5)}), "cost by plugin")["blocks"]["rows"][0]
    assert heaviest["id"] == "p"
    blind = ask(make(tmp_path, monkeypatch, solo), "cost by plugin")["blocks"]["rows"][0]
    assert blind["id"] == "m"


def test_plugin_note_counts_each_switched_off_origin_once(tmp_path, monkeypatch):
    items = [
        item("a", "alpha", origin="acme"),
        item("b", "beta", origin="gone", disabled=True),
        item("c", "gamma", origin="gone", disabled=True),
    ]
    blocks = ask(make(tmp_path, monkeypatch, items, costs={"a": cost(3)}), "cost by plugin")["blocks"]
    assert blocks["note"] == "Left out 1 switched-off plugin or pack: they cost nothing now."


def idle_items():
    return [
        item("z1", "zzz"),
        item("a1", "aaa"),
        item("m1", "mid"),
        item("n1", "none"),
        item("t1", "today"),
        item("d1", "dis", disabled=True),
    ]


def idle_extra():
    return {
        "costs": {"z1": cost(100), "a1": cost(100), "m1": cost(100), "t1": cost(100), "d1": cost(100)},
        "usage": {
            "z1": {"count": 1, "last_used": "2026-09-01"},  # 59 days
            "a1": {"count": 1, "last_used": "2026-09-25"},  # 35
            "m1": {"count": 1, "last_used": "2026-09-30"},  # 30
            "t1": {"count": 1, "last_used": "2026-10-30"},  # 0
            "d1": NEVER,
        },
        "usage_window": WINDOW,
    }


def test_since_boundaries_ordering_scope_and_fields(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, idle_items(), **idle_extra())
    reply = ask(client, "What have I not used in 30 days?")
    blocks = reply["blocks"]
    assert [(r["name"], r["value"]) for r in blocks["rows"]] == [
        ("zzz", "59 days idle; 100 tokens every session"),
        ("aaa", "35 days idle; 100 tokens every session"),
        ("mid", "30 days idle; 100 tokens every session"),
    ]  # exactly 30 days is in; today and the switched-off Item are out; the Item with no usage record is not guessed
    assert blocks["next"] == "Ask whether to keep zzz." and blocks["follow_ups"] == ["Should I keep zzz?", *FOLLOW]
    assert blocks["more"] == 0 and reply["actions"] == [{"kind": "highlight", "item_ids": ["z1", "a1", "m1"]}]
    assert blocks["note"] == (
        "Measured to 2026-10-30, the newest saved session. "
        "A never-seen Item is idle at least as long as the history (older sessions are deleted)."
    )
    assert [r["name"] for r in ask(client, "have I not used mid in 30 days")["blocks"]["rows"]] == ["mid"]
    assert [r["name"] for r in ask(client, "what have I not used in 1 day")["blocks"]["rows"]] == [
        "zzz",
        "aaa",
        "mid",
    ]  # idle 0 is not 1 day
    assert ask(client, "what have I not used in 2 weeks")["blocks"]["headline"].startswith("3 Items not used for 14 days or more")
    assert ask(client, "what have I not used in 1 month")["blocks"]["headline"].startswith("3 Items not used for 30 days or more")
    assert ask(client, "what have I not used in 3 weeks")["blocks"]["headline"].startswith("3 Items not used for 21 days or more")
    assert ask(client, "what have I not used in 2 months")["blocks"]["headline"].startswith("1 Item not used for 60 days or more") is False
    assert (
        ask(client, "what have I not used in 2 months")["blocks"]["headline"]
        == "Nothing is recorded as unused for 60 days in 41 days of past sessions."
    )
    nothing = ask(client, "what have I not used in 100 days")
    assert nothing["blocks"]["note"] is not None and nothing["blocks"]["follow_ups"] == FOLLOW and nothing["actions"] == []


def test_since_orders_equal_cost_by_idle_days_and_puts_unknown_cost_last(tmp_path, monkeypatch):
    items = [item("a1", "aaa"), item("z1", "zzz"), item("u1", "aaa-blind"), item("u2", "zzz-blind")]
    extra = {
        "costs": {"a1": cost(100), "z1": cost(100)},
        "usage": {
            "a1": {"count": 1, "last_used": "2026-09-25"},
            "z1": {"count": 1, "last_used": "2026-09-01"},
            "u1": {"count": 1, "last_used": "2026-09-25"},
            "u2": {"count": 1, "last_used": "2026-09-01"},
        },
        "usage_window": WINDOW,
    }
    rows = ask(make(tmp_path, monkeypatch, items, **extra), "what have I not used in 30 days")["blocks"]["rows"]
    assert [r["name"] for r in rows] == ["zzz", "aaa", "zzz-blind", "aaa-blind"] and rows[2]["value"] == "59 days idle; Cost unknown"
    exact = [item("a1", "aaa"), item("z1", "zzz")]
    extra = {
        "costs": {"a1": cost(100), "z1": cost(100)},
        "usage": {"a1": {"count": 1, "last_used": "2026-09-25"}, "z1": NEVER},
        "usage_window": WINDOW,
    }
    rows = ask(make(tmp_path, monkeypatch, exact, **extra), "what have I not used in 30 days")["blocks"]["rows"]
    assert [r["name"] for r in rows] == ["zzz", "aaa"] and rows[0]["value"].startswith("At least 41 days idle")
    five = [sk(n) for n in range(6)]
    for count, more in ((5, 0), (6, 1)):
        reply = ask(make(tmp_path, monkeypatch, five[:count], **unused(five[:count])), "what have I not used in 30 days")
        assert len(reply["blocks"]["rows"]) == 5 and reply["blocks"]["more"] == more and len(reply["actions"][0]["item_ids"]) == 5


def test_curly_apostrophes_are_understood(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, idle_items(), **idle_extra())
    assert ask(client, "what haven’t I used in 30 days")["blocks"]["headline"].startswith("3 Items not used for 30 days")
    assert ask(client, "Why isn’t my hook working")["blocks"]["handoff"] is not None


def test_verdict_boundaries_and_short_history_wording(tmp_path, monkeypatch):
    items = [item("a", "alpha"), item("b", "beta")]
    usage = {"a": {"count": 1, "last_used": "2026-09-30"}, "b": {"count": 1, "last_used": "2026-10-01"}}  # 30 and 29 days idle
    client = make(tmp_path, monkeypatch, items, costs={"a": cost(100), "b": cost(100)}, usage=usage, usage_window=WINDOW)
    verdict = lambda name: ask(client, f"Should I keep {name}?")["blocks"]["cards"][0]["verdict"]  # noqa: E731
    assert verdict("alpha") == {"label": "Review", "tone": "review", "why": "Not used in 30 active days"}
    assert verdict("beta")["label"] == "Keep"
    short = {"files": 2, "first": "2026-10-20", "last": "2026-10-30", "skipped": 0}
    client = make(tmp_path, monkeypatch, [item("a", "alpha")], costs={"a": cost(100)}, usage={"a": NEVER}, usage_window=short)
    assert ask(client, "Should I keep alpha?")["blocks"]["cards"][0]["verdict"]["label"] == "Not enough history yet"
    thirty = {"files": 60, "first": "2026-10-01", "last": "2026-10-30", "skipped": 0}
    client = make(tmp_path, monkeypatch, [item("a", "alpha")], costs={"a": cost(100)}, usage={"a": NEVER}, usage_window=thirty)
    assert ask(client, "Should I keep alpha?")["blocks"]["cards"][0]["verdict"]["label"] == "Could go"


def test_refusal_fields_and_wording_edges(tmp_path, monkeypatch):
    client = make(tmp_path, monkeypatch, [item("x", "pdfX"), item("q", 'say "hi"'), item("a", "alpha")])
    reply = ask(client, "Disable the plugin pdfX")["blocks"]
    assert reply["handoff"]["instruction"] == "Disable the plugin pdfX. Show me every change before you make it and wait for my OK."
    assert reply["next"] == "Copy the instruction below and paste it into Claude Code." and reply["follow_ups"] == FOLLOW
    assert ask(client, "Disable something")["blocks"]["handoff"]["instruction"].startswith("Disable something.")
    exactly = "disable " + "a" * 192  # 200 characters
    assert ask(client, exactly)["blocks"]["handoff"]["instruction"].startswith(exactly + ".")
    cut_off = ask(client, exactly + "a")["blocks"]["handoff"]["instruction"]
    assert cut_off.startswith("disable….")
    assert ask(client, "Should I keep alpha?")["blocks"]["handoff"] is None


def test_origin_sentence_per_kind(tmp_path, monkeypatch):
    for kind in ("skill", "agent", "mcp_server"):
        client = make(
            tmp_path,
            monkeypatch,
            [item("a", "alpha", kind, origin="acme/tools")],
            costs={"a": cost(100)},
            **{"usage": {"a": NEVER}, "usage_window": WINDOW},
        )
        text = ask(client, "Should I keep alpha?")["blocks"]["cards"][0]["handoff"]["instruction"]
        assert 'It came from "acme/tools": if that is a plugin or pack' in text, kind
    client = make(
        tmp_path,
        monkeypatch,
        [item("a", "alpha", "connector", origin="acme/tools")],
        costs={"a": cost(100)},
        usage={"a": NEVER},
        usage_window=WINDOW,
    )
    assert "It came from" not in ask(client, "Should I keep alpha?")["blocks"]["cards"][0]["handoff"]["instruction"]


def test_unknown_kinds_and_quoted_names_in_instructions(tmp_path, monkeypatch):
    items = [item("m", "notes", "memory"), item("q", 'say "hi"'), item("h", "pre-hook", "hook")]
    extra = {"costs": {"m": cost(100), "q": cost(100)}, "usage": {"m": NEVER, "q": NEVER}, "usage_window": WINDOW}
    client = make(tmp_path, monkeypatch, items, **extra)
    confirm = " Show me exactly what will change and wait for my OK."
    memory = ask(client, "Should I keep notes?")["blocks"]["cards"][0]["handoff"]["instruction"]
    assert memory == 'Review the memory "notes" and tell me how to remove it.' + confirm
    quoted = ask(client, "what is this", selected_ids=["q"])["blocks"]["cards"][0]["handoff"]["instruction"]
    assert quoted.startswith("Remove the skill \"say 'hi'\": find its folder")
    hook = ask(client, "Should I keep pre-hook?")["blocks"]["cards"][0]
    assert hook["verdict"]["label"] == "Not tracked"
    assert hook["handoff"]["instruction"] == 'Review the hook "pre-hook": tell me what it does and whether I still need it. Change nothing.'
