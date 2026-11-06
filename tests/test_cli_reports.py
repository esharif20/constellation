import json
import socket
from pathlib import Path

import pytest

from constellation import cli_reports
from constellation.cli import main

DEMO = Path(__file__).parent.parent / "docs" / "design" / "demo.json"
SECRET = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])  # assembled at runtime so no token-shaped string sits in the repo
READ_ONLY = [c.name for c in cli_reports.COMMANDS if c.name not in ("clean", "share")]
ARGS = {"why": ["review-diff"], "ask": ["what costs the most?"]}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("a terminal report command must not open a socket")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_doctor_on_the_demo_scan(capsys):
    code, out, _ = run(capsys, "doctor", str(DEMO))

    assert code == 0
    assert out == (
        "Constellation doctor\n\n"
        "  ✓ Session start: 5,503 tokens, 2.8% of a 200k window\n"
        "  ! Could be reclaimed: 0 to 410 tokens per session\n\n"
        "Top findings\n"
        "  - quarterly-ledger-reconciliation-helper (skill): Does the same job as review-diff; neither has been used (saves 410)\n\n"
        "Hooks and triggers\n"
        "  ✓ No clashes\n"
        "  ✓ 10 hooks, 0 able to block a prompt\n"
        "  ✓ 0 skills never fire, 0 fire greedily\n\n"
        "MCP and connectors\n"
        "  2 MCP servers, 1 connector (tool schemas are not measured)\n\n"
        "  ! 2 scan warnings in the saved scan\n"
    )


def test_cost_lists_the_biggest_first_then_by_plugin(capsys):
    _, out, _ = run(capsys, "cost", str(DEMO))

    assert out.startswith("Session-start bill\n\n  Total: 5,503 tokens (3 Items unmeasured)\n\nBiggest first\n")
    assert "  quarterly-ledger-reconciliation-helper  skill  410\n  lighthouse-lamp-maintenance-scheduler   agent  150\n" in out
    assert "\nBy plugin\n  (not in a plugin)  22 Items  1,971\n  lumen              8 Items   575\n" in out


def test_why_explains_the_verdict_and_what_refers_to_it(capsys):
    _, out, _ = run(capsys, "why", "review-diff", str(DEMO))

    assert out == (
        "review-diff (skill)\n\n  Verdict: Keep, medium confidence\n"
        "  - Its twin quarterly-ledger-reconciliation-helper could go\n"
        "  Removing it frees: unknown\n  Referred to by: critic\n  History: 0 active days\n"
    )


def test_twins_say_which_one_you_use(capsys):
    _, out, _ = run(capsys, "twins", str(DEMO))

    pair = "  ! changelog-draft and release-notes (duplicate)\n"
    assert pair + "      Same steps and trigger wording; one could go.\n      You use: neither yet\n" in out


def test_unused_waits_for_history(capsys):
    _, out, _ = run(capsys, "unused", str(DEMO))

    assert out == "No session history yet, so nothing can be called unused. Run `constellation scan` after some sessions.\n"


def test_unused_lists_unused_items_with_confidence(tmp_path, capsys):
    scan = json.loads(DEMO.read_text())
    scan["usage_window"] = {"files": 3, "first": "2026-01-01", "last": "2026-03-01"}
    scan["usage"] = {i["id"]: {"count": 0 if i["name"] == "yaml-lint" else 5, "last_used": "2026-03-01"} for i in scan["items"]}
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan))

    code, out, _ = run(capsys, "unused", str(path), "--json")

    rows = json.loads(out)["rows"]
    assert code == 0 and [r["name"] for r in rows if r["name"] == "yaml-lint"] == ["yaml-lint"]
    assert {"name", "label", "confidence", "saves"} <= rows[0].keys()


def test_explain_and_ask_use_the_same_engine_as_the_app(capsys):
    _, explained, _ = run(capsys, "explain", str(DEMO))
    _, answer, _ = run(capsys, "ask", "what costs the most?", str(DEMO))

    assert explained.startswith("# My Claude Code setup\n\n97 items")
    assert answer.startswith("quarterly-ledger-reconciliation-helper costs the most: 410 tokens every session.\n")


@pytest.mark.parametrize("name", READ_ONLY)
def test_every_read_command_has_json_output(name, capsys):
    code, out, _ = run(capsys, name, *ARGS.get(name, []), str(DEMO), "--json")

    assert code == 0
    assert isinstance(json.loads(out), dict)


@pytest.mark.parametrize("name", READ_ONLY)
def test_no_colour_codes_unless_a_terminal(name, capsys):
    _, out, _ = run(capsys, name, *ARGS.get(name, []), str(DEMO))

    assert "\033" not in out


def test_colour_only_on_a_terminal_without_no_color(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli_reports.style_for_stdout().color is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli_reports.style_for_stdout().color is False
    assert cli_reports.Style(color=True).mark(cli_reports.OK) == "\033[32m✓\033[0m"


@pytest.fixture
def secret_scan(tmp_path):
    scan = json.loads(DEMO.read_text())
    scan["items"][0]["description"] = f"Deploys with {SECRET} inline"
    scan["items"][1]["name"] = f"name-{SECRET}"
    scan["warnings"] = [f"bad token {SECRET}"]
    scan["overlaps"][0]["reason"] = f"Both use {SECRET}."
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan))
    return path, scan


@pytest.mark.parametrize("as_json", [False, True])
def test_a_planted_secret_never_appears_in_any_command(secret_scan, tmp_path, capsys, as_json):
    path, scan = secret_scan
    names = [scan["items"][0]["name"], scan["items"][1]["name"], "review-diff"]
    flag = ["--json"] if as_json else []
    for name in READ_ONLY:
        for arg in ARGS.get(name, []) if name != "why" else names:
            code, out, err = run(capsys, name, *([arg] if name in ARGS else []), str(path), *flag)
            assert SECRET not in out + err, name
            assert code in (0, 2)
    out_file = tmp_path / "cleanup.md"
    run(capsys, "clean", str(path), "--out", str(out_file))
    assert SECRET not in out_file.read_text()


def test_unknown_command_suggests_the_closest(capsys):
    code, out, err = run(capsys, "dotcor")

    assert (code, out) == (2, "")
    assert err == "Unknown command 'dotcor'. Did you mean `doctor`?\n"


def test_unknown_item_suggests_the_closest(capsys):
    code, out, err = run(capsys, "why", "revew-diff", str(DEMO))

    assert (code, out) == (2, "")
    assert err == "No Item named 'revew-diff'. Did you mean: review-diff, screenshot-diff?\n"


def test_an_ambiguous_name_asks_for_the_id(tmp_path, capsys):
    scan = json.loads(DEMO.read_text())
    clone = dict(scan["items"][0], id="skill:other:" + scan["items"][0]["name"])
    scan["items"].append(clone)
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan))

    code, _, err = run(capsys, "why", scan["items"][0]["name"], str(path))

    assert code == 2 and err.endswith("Use the id.\n") and "matches several Items" in err


@pytest.mark.parametrize("content", [None, "not json", '{"items": 3}', '{"items": [{"id": "a"}]}', "[]"])
def test_a_missing_or_unusable_scan_exits_2(tmp_path, capsys, content):
    path = tmp_path / "scan.json"
    if content is not None:
        path.write_text(content)

    code, out, err = run(capsys, "doctor", str(path))

    assert (code, out) == (2, "")
    assert err == f"{path} is missing or not a usable constellation scan; run `constellation scan` first.\n"


def test_clean_writes_a_private_checklist_and_never_overwrites(tmp_path, capsys):
    out_file = tmp_path / "cleanup.md"

    code, out, _ = run(capsys, "clean", str(DEMO), "--out", str(out_file))

    assert code == 0 and f"Wrote the removal checklist to {out_file.resolve()}\n" in out
    assert out_file.read_text().startswith("Constellation never edits your config.")
    assert oct(out_file.stat().st_mode & 0o777) == "0o600"
    code, _, err = run(capsys, "clean", str(DEMO), "--out", str(out_file))
    assert (code, err) == (2, f"{out_file} already exists; pass --force to overwrite it.\n")
    assert run(capsys, "clean", str(DEMO), "--out", str(out_file), "--force")[0] == 0


def test_help_groups_every_command(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])

    out = capsys.readouterr().out
    assert out.index("Scan and open:") < out.index("Analyse:") < out.index("Act:")
    assert all(c.name in out for c in cli_reports.COMMANDS)
