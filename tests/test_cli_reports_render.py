"""Exact renderer and builder cases: one small hand-built input per branch of each terminal command."""

import json
from pathlib import Path
from typing import Any

import pytest

from constellation import cli_reports as cr

DEMO = Path(__file__).parent.parent / "docs" / "design" / "demo.json"
PLAIN, COLOUR = cr.Style(), cr.Style(color=True)


def doctor(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session_start": {"tokens": 1000, "window": 200000, "percent": 0.5},
        "reclaimable": {"low": 0, "high": 0, "unknown": 0},
        "findings": [],
        "hooks": {"count": 1, "can_block": 0},
        "clashes": 0,
        "triggers": {"greedy": 0, "never": 0},
        "mcp": {"servers": 1, "connectors": 0},
        "warnings": 0,
    }
    return base | over


QUIET = (
    "Constellation doctor\n\n"
    "  ✓ Session start: 1,000 tokens, 0.5% of a 200k window\n"
    "  ✓ Could be reclaimed: nothing safe to remove yet\n\n"
    "Hooks and triggers\n"
    "  ✓ No clashes\n"
    "  ✓ 1 hook, 0 able to block a prompt\n"
    "  ✓ 0 skills never fire, 0 fire greedily\n\n"
    "MCP and connectors\n"
    "  1 MCP server, 0 connectors (tool schemas are not measured)\n"
)


def test_doctor_quiet():
    assert cr._r_doctor(doctor(), PLAIN) == QUIET


@pytest.mark.parametrize(("percent", "mark"), [(0.0, "✓"), (9.9, "✓"), (10.0, "!"), (24.9, "!"), (25.0, "✗"), (80.0, "✗")])
def test_doctor_session_mark_thresholds(percent, mark):
    out = cr._r_doctor(doctor(session_start={"tokens": 5, "window": 400000, "percent": percent}), PLAIN)

    assert out.splitlines()[2] == f"  {mark} Session start: 5 tokens, {percent}% of a 400k window"


def test_doctor_unmeasured_session_start():
    out = cr._r_doctor(doctor(session_start={"tokens": None, "window": 200000, "percent": None}), PLAIN)

    assert out.splitlines()[2] == "  ! Session start: not measured"


def test_doctor_reclaimable_with_unknown_sizes_and_findings():
    d = doctor(
        reclaimable={"low": 1200, "high": 3400, "unknown": 2},
        findings=[{"text": "first", "saves": 1500}, {"text": "second", "saves": None}],
    )

    assert cr._r_doctor(d, PLAIN) == (
        "Constellation doctor\n\n"
        "  ✓ Session start: 1,000 tokens, 0.5% of a 200k window\n"
        "  ! Could be reclaimed: 1,200 to 3,400 tokens per session (2 Items of unknown size not counted)\n\n"
        "Top findings\n"
        "  - first (saves 1,500)\n"
        "  - second (saves unknown)\n\n"
        "Hooks and triggers\n"
        "  ✓ No clashes\n"
        "  ✓ 1 hook, 0 able to block a prompt\n"
        "  ✓ 0 skills never fire, 0 fire greedily\n\n"
        "MCP and connectors\n"
        "  1 MCP server, 0 connectors (tool schemas are not measured)\n"
    )


def test_doctor_reclaimable_without_unknown_sizes():
    d = doctor(reclaimable={"low": 5, "high": 7, "unknown": 0})

    assert cr._r_doctor(d, PLAIN).splitlines()[3] == "  ! Could be reclaimed: 5 to 7 tokens per session"


def test_doctor_clashes_triggers_and_warnings():
    d = doctor(clashes=1, triggers={"greedy": 2, "never": 3}, hooks={"count": 4, "can_block": 2}, warnings=1)
    two = doctor(clashes=2, warnings=3)

    assert (
        cr._r_doctor(d, PLAIN)
        == QUIET.replace("  ✓ No clashes\n", "  ✗ 1 clash (run `constellation clashes`)\n")
        .replace("  ✓ 1 hook, 0 able", "  ✓ 4 hooks, 2 able")
        .replace("  ✓ 0 skills never fire, 0 fire greedily", "  ! 3 skills never fire, 2 fire greedily")
        + "\n  ! 1 scan warning in the saved scan\n"
    )
    assert "  ✗ 2 clashes (run `constellation clashes`)\n" in cr._r_doctor(two, PLAIN)
    assert cr._r_doctor(two, PLAIN).endswith("\n\n  ! 3 scan warnings in the saved scan\n")


def test_doctor_greedy_only_still_warns():
    out = cr._r_doctor(doctor(triggers={"greedy": 1, "never": 0}), PLAIN)

    assert "  ! 0 skills never fire, 1 fire greedily\n" in out


def test_doctor_colour():
    assert cr._r_doctor(doctor(clashes=1), COLOUR) == (
        "\033[1mConstellation doctor\033[0m\n\n"
        "  \033[32m✓\033[0m Session start: 1,000 tokens, 0.5% of a 200k window\n"
        "  \033[32m✓\033[0m Could be reclaimed: nothing safe to remove yet\n"
        "\n\033[1mHooks and triggers\033[0m\n"
        "  \033[31m✗\033[0m 1 clash (run `constellation clashes`)\n"
        "  \033[32m✓\033[0m 1 hook, 0 able to block a prompt\n"
        "  \033[32m✓\033[0m 0 skills never fire, 0 fire greedily\n"
        "\n\033[1mMCP and connectors\033[0m\n"
        "  1 MCP server, 0 connectors (tool schemas are not measured)\n"
    )


def test_cost_render():
    d = {
        "total": 1234,
        "unknown": 0,
        "top": [
            {"name": "alpha", "kind": "skill", "tokens": 1000},
            {"name": "b", "kind": "agent", "tokens": 5},
            {"name": "gone", "kind": "x", "tokens": None},
        ],
        "plugins": [{"name": "p", "tokens": 1005, "items": 2}, {"name": "q", "tokens": 5, "items": 1}],
    }

    assert cr._r_cost(d, PLAIN) == (
        "Session-start bill\n\n  Total: 1,234 tokens\n\nBiggest first\n"
        "  alpha  skill  1,000\n  b      agent  5\n\nBy plugin\n  p  2 Items  1,005\n  q  1 Item   5\n"
    )


def test_cost_render_empty_and_unmeasured():
    d = {"total": None, "unknown": 3, "top": [{"name": "n", "kind": "k", "tokens": None}], "plugins": []}

    assert cr._r_cost(d, PLAIN) == (
        "Session-start bill\n\n  Total: unknown tokens (3 Items unmeasured)\n\nBiggest first\n  none measured\n\nBy plugin\n  none\n"
    )
    assert cr._r_cost(d | {"top": []}, PLAIN).split("Biggest first\n")[1].startswith("  none measured\n")


def test_unused_render():
    d = {
        "sessions": 1,
        "span_days": 1,
        "active_days": 1,
        "count": 3,
        "rows": [
            {"name": "alpha", "label": "Remove", "confidence": "high", "saves": 400},
            {"name": "b", "label": "Look", "confidence": "low", "saves": None},
        ],
    }

    assert cr._r_unused(d, PLAIN) == (
        "Not used lately\n\n  History: 1 session over 1 day (1 active)\n\n"
        "  alpha  Remove  high confidence  saves 400\n  b      Look    low confidence   saves unknown\n  and 1 more\n"
    )
    assert cr._r_unused(d | {"count": 2}, PLAIN).endswith("saves unknown\n")
    assert "  and " not in cr._r_unused(d | {"count": 2}, PLAIN)


def test_unused_render_empty_and_without_history():
    d = {"sessions": 12, "span_days": 30, "active_days": 9, "count": 0, "rows": []}

    assert cr._r_unused(d, PLAIN) == "Not used lately\n\n  History: 12 sessions over 30 days (9 active)\n\n  none\n"
    assert cr._r_unused(d | {"sessions": 0}, PLAIN) == (
        "No session history yet, so nothing can be called unused. Run `constellation scan` after some sessions.\n"
    )


def test_twins_render():
    d = {
        "pairs": [
            {"a": "x", "b": "y", "verdict": "duplicate", "reason": "same", "you_use": "x"},
            {"a": "p", "b": "q", "verdict": "partial", "reason": "r", "you_use": "neither yet"},
        ]
    }

    assert cr._r_twins(d, PLAIN) == (
        "Twins\n\n  ! x and y (duplicate)\n      same\n      You use: x\n\n  ! p and q (partial)\n      r\n      You use: neither yet\n"
    )
    assert cr._r_twins({"pairs": []}, PLAIN) == "  ✓ No overlapping pairs found.\n"
    assert cr._r_twins({"pairs": []}, COLOUR) == "  \033[32m✓\033[0m No overlapping pairs found.\n"
    assert cr._r_twins(d, COLOUR).startswith("\033[1mTwins\033[0m\n\n  \033[33m!\033[0m x and y")


def why(**over: Any) -> dict[str, Any]:
    base = {
        "name": "n",
        "kind": "skill",
        "verdict": "Keep",
        "confidence": "high",
        "reasons": ["r1", "r2"],
        "frees": 120,
        "referenced_by": ["a", "b"],
        "contains": [],
        "twin": None,
        "history_days": 1,
    }
    return base | over


def test_why_render():
    assert cr._r_why(why(), PLAIN) == (
        "n (skill)\n\n  Verdict: Keep, high confidence\n  - r1\n  - r2\n"
        "  Removing it frees: 120 tokens per session\n  Referred to by: a, b\n  History: 1 active day\n"
    )


def test_why_render_all_optional_parts():
    d = why(confidence="", reasons=[], frees=None, referenced_by=[], contains=["c1", "c2"], twin="t", history_days=3)

    assert cr._r_why(d, PLAIN) == (
        "n (skill)\n\n  Verdict: Keep\n  Compared with: t\n"
        "  Removing it frees: unknown\n  Referred to by: nothing\n  Contains: c1, c2\n  History: 3 active days\n"
    )
    assert cr._r_why(why(frees=0), PLAIN).count("Removing it frees: 0 tokens per session") == 1


def test_why_render_colour_title():
    assert cr._r_why(why(), COLOUR).startswith("\033[1mn (skill)\033[0m\n\n  Verdict")


def test_hooks_render():
    hooks = [
        {"name": "guard", "phase": "pre", "can_block": True, "runs": "shell", "bytes": 1234},
        {"name": "x", "phase": "stop", "can_block": False, "runs": "mcp_tool", "bytes": None},
    ]

    assert cr._r_hooks({"hooks": hooks}, PLAIN) == (
        "Hooks, by phase and weight\n\n  guard  pre   can block  shell     1,234 B\n  x      stop             mcp_tool  unknown\n"
    )
    assert cr._r_hooks({"hooks": []}, PLAIN) == "  ✓ No hooks.\n"
    assert cr._r_hooks({"hooks": []}, COLOUR) == "  \033[32m✓\033[0m No hooks.\n"


def test_clashes_render():
    d = {
        "clashes": [
            {"kind": "hook", "key": "k", "reason": "why", "names": ["a", "b"]},
            {"kind": "mcp", "key": "z", "reason": "w2", "names": ["c"]},
        ]
    }

    assert cr._r_clashes(d, PLAIN) == "Clashes\n\n  ✗ hook: k\n      why\n      Items: a, b\n\n  ✗ mcp: z\n      w2\n      Items: c\n"
    assert cr._r_clashes({"clashes": []}, PLAIN) == "  ✓ No clashes found.\n"
    assert cr._r_clashes({"clashes": []}, COLOUR) == "  \033[32m✓\033[0m No clashes found.\n"
    assert cr._r_clashes(d, COLOUR).startswith("\033[1mClashes\033[0m\n\n  \033[31m✗\033[0m hook: k")


def test_triggers_render():
    d = {"files": 3, "rows": [{"name": "s", "flags": ["greedy", "never"], "count": 1500}, {"name": "tt", "flags": [], "count": 0}]}

    assert cr._r_triggers(d, PLAIN) == "Triggers\n\n  s   greedy never  1,500 uses\n  tt                0 uses\n"
    assert cr._r_triggers(d | {"rows": []}, PLAIN) == "  ✓ Every skill fires at a reasonable rate.\n"
    assert cr._r_triggers(d | {"rows": []}, COLOUR) == "  \033[32m✓\033[0m Every skill fires at a reasonable rate.\n"
    assert cr._r_triggers(d | {"files": 0}, PLAIN) == "Usage was not read in this scan, so trigger behaviour is unknown.\n"
    assert cr._r_triggers({"files": 0, "rows": [{}]}, PLAIN).startswith("Usage was not")


def test_text_render_prefers_text_over_answer():
    assert cr._r_text({"text": "T", "answer": "A"}, PLAIN) == "T"
    assert cr._r_text({"answer": "A"}, PLAIN) == "A\n"


def test_command_tables_cover_the_read_only_commands():
    names = [c.name for c in cr.COMMANDS if c.name not in ("clean", "share")]

    assert list(cr.RENDER) == names == list(cr.BUILD)


def test_scrub_redacts_strings_at_any_depth_and_keeps_numbers():
    secret = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])
    out = cr._scrub({"a": [secret, (secret, 4)], "b": {"c": secret, "d": 1.5, "e": None, "f": True}})

    assert secret not in json.dumps(out)
    assert out["a"][1][1] == 4 and out["b"]["d"] == 1.5 and out["b"]["e"] is None and out["b"]["f"] is True
    assert isinstance(out["a"][1], list)


def test_run_json_is_indented_and_redacted_and_text_goes_through_the_renderer():
    s = cr.load(DEMO)

    as_json = cr.run("hooks", s, None, as_json=True, st=PLAIN)
    assert as_json == json.dumps(cr._hooks(s, None), indent=2) + "\n"
    assert cr.run("hooks", s, None, as_json=False, st=PLAIN) == cr._r_hooks(cr._hooks(s, None), PLAIN)
