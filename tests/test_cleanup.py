import os
import re
import stat

import pytest

from constellation import cleanup
from constellation.assessment import Assessed
from constellation.cli_reports import Scan, Style
from constellation.keys import Action
from constellation.verdict_types import Assessment, Evidence, ItemEvidence, Reason

PLAIN = Style(False, 80)


def assessment(id_, tier, label, conf, saves, *reasons):
    return Assessment(id_, tier, label, conf, tuple(Reason("c", r) for r in reasons), "none", saves, 1, None, None)


def fake_scan():
    items = [
        {"id": "p:lumen", "kind": "plugin", "name": "lumen"},
        {"id": "s:a", "kind": "skill", "name": "alpha"},
        {"id": "s:b", "kind": "skill", "name": "bravo"},
        {"id": "s:c", "kind": "skill", "name": "charlie"},
        {"id": "s:d", "kind": "skill", "name": "delta"},
        {"id": "s:e", "kind": "skill", "name": "echo"},
        {"id": "g:f", "kind": "agent", "name": "foxtrot"},
        {"id": "s:g", "kind": "skill", "name": "golf"},
        {"id": "s:h", "kind": "skill", "name": "hotel"},
    ]
    found = {
        "s:a": assessment("s:a", "redundant", "Likely redundant", "medium", 100, "Same job as bravo", "second"),
        "s:b": assessment("s:b", "could_go", "Could go", "high", 50, "Never used"),
        "s:c": assessment("s:c", "review", "Review", "low", None, "Short description"),
        "s:d": assessment("s:d", "keep", "Keep", "high", 70, "Pinned"),
        "s:e": assessment("s:e", "keep", "Keep", "high", 900, "Used daily"),
        "g:f": assessment("g:f", "review", "Review", "low", 10, "Vague"),
        "s:g": assessment("s:g", "off", "Off", None, 5, "Disabled"),
        "s:h": assessment("s:h", "off", "Off", None, None, "Disabled"),
    }
    ev = {i: ItemEvidence() for i in found} | {"s:d": ItemEvidence(pinned=True), "s:h": ItemEvidence(pinned=True)}
    del ev["s:g"]
    rel = [{"source": "p:lumen", "target": t, "kind": "contains"} for t in ("s:a", "s:b", "s:d")]
    data = {"items": items, "relations": rel}
    return Scan(data, Assessed(found, Evidence(5, 3, 7, 1.0, {}, 0.0, ev), False))


def test_proposals_group_by_plugin_then_kind_and_never_propose_pinned_items():
    proposed, protected = cleanup.proposals(fake_scan())
    assert [(p.name, p.group, p.label, p.confidence, p.saves, p.reasons) for p in proposed] == [
        ("alpha", "lumen", "Likely redundant", "medium", 100, ("Same job as bravo", "second")),
        ("bravo", "lumen", "Could go", "high", 50, ("Never used",)),
        ("foxtrot", "agent", "Review", "low", 10, ("Vague",)),
        ("charlie", "skill", "Review", "", None, ("Short description",))
        if False
        else ("charlie", "skill", "Review", "low", None, ("Short description",)),
    ]
    assert [(p.name, p.group, p.confidence) for p in protected] == [("delta", "lumen", "high"), ("hotel", "skill", "")]
    assert proposed[0].tier == "redundant" and proposed[1].tier == "could_go" and proposed[2].tier == "review"
    assert proposed[0].id == "s:a"


def test_groups_order_by_subtotal_then_name_and_sort_items_by_saving():
    mk = lambda n, g, s: cleanup.Prop(n, n, g, "review", "Review", "low", s, ("r",))  # noqa: E731
    props = [mk("x", "b", 5), mk("y", "a", 5), mk("z", "c", 9), mk("w", "b", None), mk("v", "b", 7)]
    got = cleanup._groups(props)
    assert [g[0] for g in got] == ["b", "c", "a"] and [g[2] for g in got] == [12, 9, 5]
    assert [p.name for p in got[0][1]] == ["v", "x", "w"]
    tie = cleanup._groups([mk("m", "q", 3), mk("n", "p", 3)])
    assert [g[0] for g in tie] == ["p", "q"]


def test_reclaimable_uses_the_verdict_totals():
    assert cleanup.reclaimable(fake_scan()) == (0, 0, 0)


def test_step_keys():
    assert cleanup.step(0, "up", 3) == 0 and cleanup.step(2, "up", 3) == 1
    assert cleanup.step(2, "down", 3) == 2 and cleanup.step(0, "down", 3) == 1
    assert cleanup.step(1, "ctrl-c", 3) == Action("interrupt")
    for key, kind in [("enter", "why"), ("right", "why"), (" ", "toggle"), ("p", "pin"), ("a", "write"), ("esc", "back"), ("q", "back")]:
        assert cleanup.step(1, key, 3) == Action(kind, 1)
    assert cleanup.step(0, "q", 0) == Action("back", 0)
    for key in ("enter", " ", "p", "a", "x"):
        assert cleanup.step(0, key, 0) == 0
    assert cleanup.step(1, "x", 3) == 1


def test_headline_sums_checked_savings_and_names_the_range():
    props = [
        cleanup.Prop("a", "a", "g", "review", "Review", "low", 100, ("r",)),
        cleanup.Prop("b", "b", "g", "review", "Review", "low", 50, ("r",)),
    ]
    assert cleanup.headline(props, frozenset({"a"}), (10, 400, 0)) == "Could free ~100 tokens per session (10 to 400)"
    assert cleanup.headline(props, frozenset(), (0, 0, 2)) == "Could free ~0 tokens per session (0 to 0; 2 unmeasured)"
    assert cleanup.headline(props, frozenset({"a", "b"}), (0, 1500, 0)).startswith("Could free ~150 tokens")


def view():
    return cleanup.View(fake_scan())


def test_render_exact_frame_with_groups_subtotals_and_protected():
    v = view()
    assert "\n".join(v.lines(1, PLAIN)) == (
        "Clean  (dry run: nothing is deleted)\n"
        "Could free ~160 tokens per session (0 to 0)\n"
        "\n"
        "  lumen  2 Items, ~150 tokens\n"
        "    [x] alpha  Likely redundant · medium · 100 · Same job as bravo\n"
        "  ▶ [x] bravo  Could go · high · 50 · Never used\n"
        "  agent  1 Item, ~10 tokens\n"
        "    [x] foxtrot  Review · low · 10 · Vague\n"
        "  skill  1 Item, ~0 tokens\n"
        "    [x] charlie  Review · low · unknown · Short description\n"
        "  Protected (pinned)  2 Items\n"
        "    [-] delta  pinned: kept\n"
        "    [-] hotel  pinned: kept\n"
        "\n"
        "↑↓ | Enter Why | Space Toggle | P Pin | A Write checklist | Esc/Q Back"
    )


def test_toggle_flips_proposed_items_only_and_updates_the_headline():
    v = view()
    assert v.key(1, " ") == 1
    assert [p.name for p in v.chosen()] == ["alpha", "foxtrot", "charlie"]
    assert "[ ] bravo" in "\n".join(v.lines(0, PLAIN)) and "~110 tokens" in v.lines(0, PLAIN)[1]
    assert v.key(1, " ") == 1 and len(v.chosen()) == 4
    assert v.key(4, " ") == 4 and v.key(5, " ") == 5  # the pinned Items cannot be checked
    assert v.checked == frozenset({"s:a", "s:b", "g:f", "s:c"})
    assert v.key(0, "down") == 1 and v.key(0, "enter") == Action("why", 0)


def test_view_keeps_the_choice_across_a_rebuild_and_drops_ids_no_longer_proposed():
    v = cleanup.View(fake_scan(), frozenset({"s:a", "s:d", "gone"}))
    assert v.checked == frozenset({"s:a"})
    assert cleanup.View(fake_scan(), frozenset()).checked == frozenset()


def test_render_scrolls_a_window_around_the_selection():
    props = [cleanup.Prop(f"p{i}", f"p{i}", "g", "review", "Review", "low", 1, ("r",)) for i in range(10)]
    ids = frozenset(p.id for p in props)

    def shown(index, size):
        lines = cleanup.render(props, 10, ids, index, PLAIN, (0, 0, 0), size)
        assert len(lines) == size + 5
        return [m[1] for line in lines[3:-2] if (m := re.search(r"\[x\] (\w+)", line))]

    assert shown(0, 4) == ["p0", "p1", "p2"]  # the group header takes the first line
    assert shown(5, 4) == ["p3", "p4", "p5", "p6"]
    assert shown(9, 4) == ["p6", "p7", "p8", "p9"]
    assert len(cleanup.render(props[:1], 1, ids, 0, PLAIN, (0, 0, 0), 14)) == 7  # a short list is not padded


def test_render_colours_tiers_and_the_selected_row():
    lines = cleanup.View(fake_scan()).lines(0, Style(True, 80))
    assert lines[0] == "\033[1;" + cleanup.MAGENTA + "mClean\033[0m\033[2m  (dry run: nothing is deleted)\033[0m"
    assert lines[4] == "\033[" + cleanup.RED + "m  ▶ [x] alpha  Likely redundant · medium · 100 · Same job as bravo\033[0m"
    assert lines[5] == "    [x] bravo  \033[" + cleanup.AMBER + "mCould go · high · 50 · Never used\033[0m"
    assert lines[7] == "    [x] foxtrot  \033[" + cleanup.BLUE + "mReview · low · 10 · Vague\033[0m"
    assert lines[11] == "    [-] delta  \033[2mpinned: kept\033[0m"
    assert lines[3] == "\033[1m  lumen\033[0m\033[2m  2 Items, ~150 tokens\033[0m"
    assert "\033" not in "".join(view().lines(0, PLAIN))


def test_render_narrow_and_empty():
    narrow = cleanup.View(fake_scan()).lines(0, Style(False, 40))
    assert all(len(line) <= 40 for line in narrow)
    empty = cleanup.render([], 0, frozenset(), 0, PLAIN, (0, 0, 0))
    assert empty == [
        "Clean  (dry run: nothing is deleted)",
        "Could free ~0 tokens per session (0 to 0)",
        "",
        "",
        "↑↓ | Enter Why | Space Toggle | P Pin | A Write checklist | Esc/Q Back",
    ]


def test_why_text_lists_every_reason_and_protected_items():
    proposed, protected = cleanup.proposals(fake_scan())
    text = cleanup.why_text(proposed, protected, (0, 160, 1), PLAIN)
    assert text == (
        "Clean: dry run (nothing is deleted)\n"
        "\n"
        "  Could free ~160 tokens per session (0 to 160; 1 unmeasured)\n"
        "\n"
        "lumen  (2 Items, ~150 tokens)\n"
        "  alpha: Likely redundant, medium confidence, saves 100\n"
        "      - Same job as bravo\n"
        "      - second\n"
        "  bravo: Could go, high confidence, saves 50\n"
        "      - Never used\n"
        "\n"
        "agent  (1 Item, ~10 tokens)\n"
        "  foxtrot: Review, low confidence, saves 10\n"
        "      - Vague\n"
        "\n"
        "skill  (1 Item, ~0 tokens)\n"
        "  charlie: Review, low confidence, saves unknown\n"
        "      - Short description\n"
        "\n"
        "Protected (pinned)  (2)\n"
        "  delta: kept because you pinned it\n"
        "  hotel: kept because you pinned it\n"
    )
    assert cleanup.why_text([], [], (0, 0, 0), PLAIN) == (
        "Clean: dry run (nothing is deleted)\n\n  Could free ~0 tokens per session (0 to 0)\n\n  Nothing to propose.\n"
    )
    assert "Protected" not in cleanup.why_text(proposed, [], (0, 0, 0), PLAIN)
    assert "(1 Item," in cleanup.why_text(proposed[:1], [], (0, 0, 0), PLAIN)


def test_checklist_text_and_write_new_never_overwrites(tmp_path):
    proposed, _ = cleanup.proposals(fake_scan())
    text = cleanup.checklist(proposed[:2])
    assert text == (
        "Constellation never edits your config. Every change below is yours to make by hand.\n\n"
        "# Constellation cleanup checklist\n\n## Chosen in the Clean view\n\n"
        "- [ ] alpha (lumen): Same job as bravo Saves 100 always-on tokens.\n"
        "- [ ] bravo (lumen): Never used Saves 50 always-on tokens.\n"
    )
    assert cleanup.checklist([]).endswith("None chosen.\n")
    assert "Saves unknown always-on" in cleanup.checklist(proposed[3:])
    path = tmp_path / "c.md"
    cleanup.write_new(path, "one")
    assert path.read_text() == "one" and stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with pytest.raises(FileExistsError):
        cleanup.write_new(path, "two")
    assert path.read_text() == "one"


def test_the_demo_scan_has_proposals_and_a_range():
    from pathlib import Path

    from constellation import cli_reports

    scan = cli_reports.load(Path(__file__).parent.parent / "docs" / "design" / "demo-assess.json")
    proposed, protected = cleanup.proposals(scan)
    assert proposed and protected == []
    assert cleanup.reclaimable(scan) == (0, 2442, 1)


def test_clean_dry_run_why_prints_every_reason_and_writes_nothing(tmp_path, monkeypatch, capsys):
    import shutil
    from pathlib import Path

    from constellation import cli

    monkeypatch.chdir(tmp_path)
    shutil.copy(Path(__file__).parent.parent / "docs" / "design" / "demo-assess.json", tmp_path / "constellation.json")
    assert cli.main(["clean", "--dry-run"]) == 0
    plain = capsys.readouterr().out
    assert "Clean: dry run" not in plain
    assert cli.main(["clean", "--dry-run", "--why"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(plain) and "Clean: dry run (nothing is deleted)" in out
    assert "quarterly-ledger-reconciliation-helper: Likely redundant, medium confidence, saves 410" in out
    assert "      - Does the same job as review-diff; neither has been used" in out
    assert not (tmp_path / "cleanup.md").exists()
    assert cli.main(["clean", "--why"]) == 2
    assert "--why needs --dry-run." in capsys.readouterr().err
    assert not (tmp_path / "cleanup.md").exists()


def test_groups_sort_unknown_savings_after_known_ones():
    mk = lambda n, s: cleanup.Prop(n, n, "g", "review", "Review", "low", s, ("r",))  # noqa: E731
    assert [p.name for p in cleanup._groups([mk("a", None), mk("b", 1), mk("c", 0)])[0][1]] == ["b", "a", "c"]


def test_fit_cuts_at_the_width_with_an_ellipsis():
    assert cleanup._fit("abcde", 5) == "abcde"
    assert cleanup._fit("abcdef", 5) == "abcd…"


def test_default_window_is_fourteen_lines_of_the_list():
    props = [cleanup.Prop(f"p{i}", f"p{i}", "g", "review", "Review", "low", 1, ("r",)) for i in range(30)]
    lines = cleanup.render(props, 30, frozenset(), 0, PLAIN, (0, 0, 0))
    assert len(lines) == 14 + 5 and lines[3].startswith("  g")


def test_colours_the_headline_and_footer_dim():
    lines = cleanup.render([], 0, frozenset(), 0, Style(True, 80), (0, 0, 0))
    assert lines[1] == "\033[2mCould free ~0 tokens per session (0 to 0)\033[0m"
    assert lines[-1] == "\033[2m" + cleanup.FOOTER + "\033[0m"
