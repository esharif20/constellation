import io
import json
from pathlib import Path

from constellation import scanfile
from constellation.cli import main
from constellation.progress import ProgressEvent, Reporter, render_bar


def test_render_bar_exact_plain_with_eta():
    event = ProgressEvent("usage", 87, 212, 4_100_000)
    assert render_bar(event, 16, 0.0, 10.0, False) == "[██████░░░░░░░░░░] 41%  reading transcripts 87/212 files 4.1 MB  ~15s left"


def test_render_bar_hides_eta_before_two_seconds_and_when_done():
    event = ProgressEvent("skills", 3, 12)
    assert render_bar(event, 8, 0.0, 1.99, False) == "[██░░░░░░] 25%  reading config and skills 3/12"
    assert render_bar(event, 8, 0.0, 2.0, False).endswith("3/12  ~6s left")
    assert render_bar(ProgressEvent("skills", 12, 12), 8, 0.0, 99.0, False) == "[████████] 100%  reading config and skills 12/12"


def test_render_bar_minutes_unknown_total_and_color():
    assert render_bar(ProgressEvent("usage", 1, 100), 4, 0.0, 1.5, False).endswith("~1s left") is False
    assert render_bar(ProgressEvent("usage", 1, 100), 4, 0.0, 2.0, False).endswith("~3m18s left")
    assert render_bar(ProgressEvent("write", 0, 0), 4, 0.0, 9.0, False) == "[░░░░] 0%  writing"
    assert render_bar(ProgressEvent("mcp", 1, 2), 2, 0.0, 0.0, True) == "[\x1b[32m█\x1b[2m░\x1b[0m] 50%  reading hooks/MCP 1/2"


def test_reporter_tty_redraws_one_line_and_restores_cursor():
    out, now = io.StringIO(), [0.0]
    with Reporter("Scanning ~/.claude", True, False, 100, out, lambda: now[0]) as report:
        report(ProgressEvent("usage", 1, 4))
        now[0] = 0.05
        report(ProgressEvent("usage", 2, 4))  # inside the redraw interval: skipped
        now[0] = 3.0
        report(ProgressEvent("usage", 3, 4))
    assert out.getvalue() == (
        "\x1b[?25l"
        "\r" + "Scanning ~/.claude  [████░░░░░░░░░░░░] 25%  reading transcripts 1/4 files\x1b[K"
        "\r" + "Scanning ~/.claude  [████████████░░░░] 75%  reading transcripts 3/4 files  ~1s left\x1b[K"
        "\r\x1b[K\x1b[?25h"
    )


def test_reporter_restores_cursor_on_ctrl_c():
    out = io.StringIO()
    try:
        with Reporter("t", True, False, 100, out):
            raise KeyboardInterrupt
    except KeyboardInterrupt:
        pass
    assert out.getvalue().endswith("\x1b[?25h")


def test_reporter_non_tty_prints_one_plain_line_per_phase():
    out = io.StringIO()
    with Reporter("t", False, False, 100, out) as report:
        report(ProgressEvent("skills", 1, 3))
        report(ProgressEvent("skills", 212, 212))
        report(ProgressEvent("usage", 0, 5))
    assert out.getvalue() == "reading config and skills… 212\nreading transcripts… 0\n"


def test_latest_scan_prefers_explicit_then_local_then_remembered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert scanfile.latest_scan() == Path("constellation.json")  # nothing yet
    saved = tmp_path / "elsewhere.json"
    saved.write_text("{}")
    scanfile.remember(saved)
    assert scanfile.latest_scan() == saved.resolve()
    Path("constellation.json").write_text("{}")
    Path("constellation.json").chmod(0o600)
    assert scanfile.latest_scan() == Path("constellation.json")
    assert scanfile.latest_scan(Path("given.json")) == Path("given.json")
    Path("constellation.json").unlink()
    saved.unlink()
    assert scanfile.latest_scan() == Path("constellation.json")  # a remembered file that vanished is ignored


def test_scan_alone_works_and_later_commands_find_the_scan(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    skill = Path.home() / ".claude" / "skills" / "tidy"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: tidy\ndescription: Tidy up files\n---\nBody\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert main(["scan"]) == 0
    out = capsys.readouterr()
    target = Path.home() / ".cache" / "constellation" / "scan.json"
    assert target.is_file() and (tmp_path / "constellation.json").exists() is False
    assert "Saved ~/.cache/constellation/scan.json (1 Items, " in out.out and out.out.rstrip().endswith("Next: constellation open")
    assert "reading config and skills… " in out.err and "read origin" not in out.err

    assert main(["status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)

    assert main(["scan", "-q"]) == 0
    quiet = capsys.readouterr()
    assert quiet.out == "" and "reading" not in quiet.err
