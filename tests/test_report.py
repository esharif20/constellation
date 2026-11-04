import copy
import json
import os
import stat
from pathlib import Path

import pytest

from constellation.cli import main
from constellation.report import NOTE, _fit, render_cleanup, render_report

FIXTURE = Path(__file__).parent / "fixtures" / "scan.json"
SECRET = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])


@pytest.fixture
def data():
    return json.loads(FIXTURE.read_text())


def report(data, *, top=15, color=False, width=80, show_all=False):
    return render_report(data, top=top, color=color, width=width, show_all=show_all)


def test_cli_prints_report_with_no_network_or_key(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    code = main(["report", str(FIXTURE)])

    out = capsys.readouterr().out
    assert code == 0
    assert "deploy (skill) and ship (skill)" in out
    assert "\033" not in out  # piped: no colour
    assert max(len(line) for line in out.splitlines()) <= 80


def test_cli_defaults_to_constellation_json_in_cwd(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "constellation.json").write_text(FIXTURE.read_text())

    assert main(["report"]) == 0
    assert "Constellation report" in capsys.readouterr().out


@pytest.mark.parametrize("content", [None, "not json", "[1, 2]", '{"no": "items"}', '{"items": 3}'])
def test_cli_missing_or_invalid_file_exits_2(tmp_path, capsys, content):
    path = tmp_path / "scan.json"
    if content is not None:
        path.write_text(content)

    assert main(["report", str(path)]) == 2
    assert "scan.json" in capsys.readouterr().err


def test_cli_top_and_all_flags(capsys):
    main(["report", str(FIXTURE), "--top", "2", "--all"])

    out = capsys.readouterr().out
    assert "release-notes (skill)\n" not in out.split("Overlaps")[0]
    assert "distinct (1)" in out


def test_cli_color_only_on_a_tty_without_no_color(monkeypatch, capsys):
    class Tty:
        def isatty(self):
            return True

        def write(self, text):
            return len(text)

        def flush(self):
            pass

    monkeypatch.setattr("sys.stdout", Tty())
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert main(["report", str(FIXTURE)]) == 0  # smoke: a tty stdout works
    monkeypatch.setenv("NO_COLOR", "1")
    assert main(["report", str(FIXTURE)]) == 0


def test_cli_colour_decision(monkeypatch):
    seen = []
    monkeypatch.setattr("constellation.cli.render_report", lambda data, **kw: seen.append(kw["color"]) or "")
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    main(["report", str(FIXTURE)])
    monkeypatch.setenv("NO_COLOR", "")
    main(["report", str(FIXTURE)])
    assert seen == [True, False]  # NO_COLOR set at all (even empty) turns colour off


def test_cleanup_writes_private_checklist_and_only_that(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    code = main(["report", str(FIXTURE), "--cleanup", "cleanup.md", "--top", "2"])

    text = (tmp_path / "cleanup.md").read_text()
    assert code == 0
    assert text.splitlines()[0].startswith("Constellation never edits your config")
    assert "- [ ] Review and remove one of these two: deploy (skill) and ship (skill)." in text
    assert "- [ ] deploy (skill): 420 tokens" in text
    assert "release-notes" not in text
    assert stat.S_IMODE(os.stat(tmp_path / "cleanup.md").st_mode) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cleanup.md"]


def test_cleanup_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cleanup.md").write_text("mine")

    assert main(["report", str(FIXTURE), "--cleanup", "cleanup.md"]) == 2
    assert (tmp_path / "cleanup.md").read_text() == "mine"
    assert "--force" in capsys.readouterr().err

    assert main(["report", str(FIXTURE), "--cleanup", "cleanup.md", "--force"]) == 0
    assert (tmp_path / "cleanup.md").read_text() != "mine"
    assert stat.S_IMODE(os.stat(tmp_path / "cleanup.md").st_mode) == 0o600


def test_cleanup_without_costs_or_duplicates(data):
    data["costs"], data["overlaps"] = None, []
    text = render_cleanup(data, top=5)
    assert "None found." in text
    assert "Token costs were not measured." in text


def test_top_items_are_ordered_by_cost_then_name(data):
    out = report(data).split("Overlaps")[0]
    order = [out.index(n) for n in ("deploy (skill)", "ship (skill)", "release-notes", "review (skill)", "reviewer", "changelog")]
    assert order == sorted(order)
    data["costs"]["skill:ship"]["always_on"] = 420  # tie: name order breaks it
    out = report(data)
    assert out.index("deploy (skill)") < out.index("ship (skill)")
    data["items"][0]["name"] = "zzz"
    assert report(data).index("ship (skill)") < report(data).index("zzz (skill)")


def test_top_limits_rows_and_numbers_them(data):
    out = report(data, top=2)
    assert " 1  " in out and " 2  " in out and " 3  " not in out
    assert "changelog (command)" not in out.split("Overlaps")[0]


def test_unknown_cost_is_not_counted_as_zero(data):
    out = report(data)
    assert "Total always-on: 1,210 tokens across 6 Items; 2 Items have unknown cost" in out
    assert "format-on-save" not in out.split("Overlaps")[0]  # unknown is not ranked as a zero-cost Item


def test_zero_cost_item_is_known_and_has_no_bar(data):
    data["costs"]["skill:review"]["always_on"] = 0
    out = report(data)
    assert "across 6 Items; 2 Items" in out
    assert any(line.split()[:2] == ["6", "0"] and "#" not in line for line in out.splitlines())


def test_offline_scan_with_null_costs_and_no_labels(data):
    data["costs"], data["labels"], data["clusters"] = None, {}, []
    out = report(data)
    assert "Token costs were not measured in this scan." in out
    assert "Total always-on: 0 tokens across 0 Items; 8 Items have unknown cost" in out
    assert "cluster" not in out


def test_missing_cost_entries_are_unknown(data):
    data["costs"] = {"skill:deploy": {"always_on": 10, "on_use": None}, "skill:ship": None}
    assert "10 tokens across 1 Items; 7 Items" in report(data)


def test_bar_scales_to_the_biggest_item(data):
    lines = {line.split()[1]: line for line in report(data).splitlines() if line[:2].strip().isdigit()}
    assert lines["420"].count("#") == 10 and lines["180"].count("#") == 4 and lines["40"].count("#") == 1


def test_cluster_label_and_description_shown(data):
    out = report(data)
    assert "      cluster deploy · purpose ships code to production\n" in out
    assert "      Ship the current branch to production with the release checklist.\n" in out


def test_overlaps_grouped_duplicate_then_wrapper_then_overlap_names_not_ids(data):
    out = report(data)
    assert out.index("duplicate (1)") < out.index("wrapper (1)") < out.index("overlap (1)")
    assert "reviewer (agent) wraps review (skill)" in out
    assert "skill:deploy" not in out
    assert "distinct (" not in out and "(1 distinct hidden; use --all to show them)" in out


def test_all_shows_distinct_last_and_drops_the_hint(data):
    out = report(data, show_all=True)
    assert out.index("overlap (1)") < out.index("distinct (1)")
    assert "One reads diffs" in out and "hidden" not in out


def test_no_overlaps(data):
    data["overlaps"] = None
    assert "  None found." in report(data)
    data["overlaps"] = [o for o in json.loads(FIXTURE.read_text())["overlaps"] if o["verdict"] == "distinct"]
    out = report(data)
    assert "None found." in out and "(1 distinct hidden" in out
    assert "None found." not in report(data, show_all=True)


def test_overlap_with_unknown_id_falls_back_to_the_id(data):
    data["overlaps"] = [{"a_id": "gone:1", "b_id": "skill:ship", "verdict": "duplicate", "reason": "x"}]
    assert "gone:1 and ship (skill)" in report(data)


def test_warnings_listed_sorted_or_none(data):
    out = report(data)
    assert out.index("could not read") < out.index("mcp server github")
    data["warnings"] = []
    assert "Warnings" in report(data) and "  None.\n" in report(data)


def test_header_counts(data):
    out = report(data)
    assert "Items: 8 (agent 1, command 1, hook 1, mcp 1, skill 4)" in out
    assert "Relations: 1   Clusters: 2" in out
    data["relations"] = None
    del data["clusters"]
    assert "Relations: 0   Clusters: 0" in report(data)


@pytest.mark.parametrize("width", [40, 60, 80])
def test_wraps_long_reasons_and_never_exceeds_width(data, width):
    data["overlaps"][0]["reason"] = "word " * 60
    data["warnings"].append("warn " * 60)
    data["items"][0]["description"] = "desc " * 60
    out = report(data, width=width, show_all=True)
    assert max(len(line) for line in out.splitlines()) <= width
    assert out.count("word") == 60 and out.count("warn") == 60


def test_long_name_is_truncated_with_an_ellipsis(data):
    data["items"][0]["name"] = "n" * 200
    line = next(line for line in report(data).splitlines() if "nnnn" in line)
    assert len(line) == 80 and line.endswith("…")


def test_no_ansi_without_colour_and_ansi_with_it(data):
    assert "\033" not in report(data, show_all=True)
    assert "█" not in report(data)
    coloured = report(data, color=True, show_all=True)
    assert "\033[1mConstellation report\033[0m" in coloured
    assert "█" in coloured and "─" in coloured and "#" not in coloured.split("Overlaps")[0]
    for verdict, code in (("duplicate", 31), ("wrapper", 33), ("overlap", 36), ("distinct", 32)):
        assert f"\033[{code}m  {verdict} (1)\033[0m" in coloured
    assert "\033[2m" in coloured


def test_coloured_lines_still_fit_the_width(data):
    plain = [len(line) for line in report(data, color=False).splitlines()]
    stripped = [len(line) for line in report(data, color=True).replace("█", "#").replace("─", "-").splitlines()]
    assert max(plain) <= 80  # ANSI codes add to len(), so compare visible text only
    assert len(stripped) == len(plain)


def test_secret_in_description_reason_and_warning_is_redacted(data):
    data["items"][0]["description"] = f"Deploys using {SECRET} inline"
    data["overlaps"][1]["reason"] = f"Both use {SECRET}"
    data["warnings"].append(f"bad token {SECRET}")
    out = report(data, show_all=True)
    assert SECRET not in out and "[REDACTED]" in out
    data["overlaps"][1]["reason"] = f"Both use {SECRET}"
    assert SECRET not in render_cleanup(data, top=3)


def test_redaction_note_is_in_the_report(data):
    assert NOTE.split(";")[0] in report(data)


def test_deterministic_and_does_not_mutate_input(data):
    before = copy.deepcopy(data)
    first = report(data, show_all=True)
    shuffled = copy.deepcopy(data)
    shuffled["overlaps"].reverse()
    shuffled["warnings"].reverse()
    assert report(shuffled, show_all=True) == first == report(data, show_all=True)
    assert data == before


def test_heading_rule_fills_the_width(data):
    heading = next(line for line in report(data).splitlines() if line.startswith("Overlaps"))
    assert heading == "Overlaps " + "-" * 71
    assert next(line for line in report(data, color=True).splitlines() if "Overlaps" in line).count("─") == 71


# Golden outputs: the whole rendering is the contract, so a changed character anywhere is a visible diff.
@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        ("report.txt", dict(top=15, color=False, width=80, show_all=True)),
        ("report_color.txt", dict(top=3, color=True, width=60, show_all=False)),
    ],
)
def test_golden_report(data, name, kwargs):
    assert render_report(data, **kwargs) == (FIXTURE.parent / name).read_text()


def test_golden_cleanup(data):
    assert render_cleanup(data, top=3) == (FIXTURE.parent / "cleanup.md").read_text()


def test_fit_keeps_text_that_exactly_fits():
    assert _fit("abc", 3) == "abc" and _fit("abcd", 3) == "ab…"


def test_empty_states_are_plain_lines_in_report_and_cleanup(data):
    data["costs"], data["overlaps"] = None, []
    assert "  Token costs were not measured in this scan." in report(data).splitlines()
    assert "  None found." in report(data).splitlines()
    assert "Token costs were not measured." in render_cleanup(data, top=3).splitlines()
    assert "None found." in render_cleanup(data, top=3).splitlines()


def test_second_id_of_an_unknown_overlap_falls_back_to_the_id(data):
    data["overlaps"] = [{"a_id": "skill:ship", "b_id": "gone:2", "verdict": "duplicate", "reason": "x"}]
    assert "ship (skill) and gone:2" in report(data)
