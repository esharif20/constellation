import contextlib
import importlib.metadata
from pathlib import Path

import pytest

from constellation import cli, menu
from constellation.cli_reports import Style

PLAIN = Style(False, 80)
VERSION = importlib.metadata.version("constellation-cli")


def keys_of(*keys):
    return iter(keys)


def drive(*keys, lines_for=None):
    out = []
    action = menu.choose(keys_of(*keys), out.append, lines_for or (lambda i: [f"row{i}"]))
    return action, out


def test_step_navigation_and_bounds():
    assert menu.step(0, "up") == 0
    assert menu.step(1, "up") == 0
    assert menu.step(3, "up") == 2
    assert menu.step(0, "down") == 1
    assert menu.step(4, "down") == 5
    assert menu.step(5, "down") == 5
    assert menu.step(2, "x") == 2
    assert menu.step(2, "") == 2


def test_step_digits_select_within_range():
    assert menu.step(3, "1") == 0
    assert menu.step(0, "6") == 5
    assert menu.step(2, "0") == 2
    assert menu.step(2, "7") == 2
    assert menu.step(2, "²") == 2
    assert menu.step(2, "") == 2


def test_step_actions():
    assert menu.step(2, "enter") == menu.Action("run", 2)
    assert menu.step(2, "q") == menu.Action("quit", 0)
    assert menu.step(2, "h") == menu.Action("help", 0)
    assert menu.step(2, "ctrl-c") == menu.Action("interrupt", 0)


def test_down_down_enter_is_clean():
    action, _ = drive("down", "down", "enter")
    assert action == menu.Action("run", 2)


def test_choose_redraws_over_the_previous_frame():
    action, out = drive("down", "q", lines_for=lambda i: [f"a{i}", f"b{i}"])
    assert action.kind == "quit"
    assert out == ["a0\r\nb0\r\n", "\033[2F\033[Ja1\r\nb1\r\n"]


def test_choose_quits_when_keys_run_out():
    assert drive()[0] == menu.Action("quit")


@pytest.mark.parametrize(
    "data,key",
    [
        (b"\x1b[A", "up"),
        (b"\x1b[B", "down"),
        (b"\r", "enter"),
        (b"\n", "enter"),
        (b"\x03", "ctrl-c"),
        (b"\x04", "q"),
        (b"Q", "q"),
        (b"3", "3"),
        (b"\x1b[C", ""),
        (b"", "q"),
        (b"\x80", ""),
        (b"\x7f", "\x7f"),
        (b"ab", ""),
        (b"\xff", ""),
    ],
)
def test_parse_key(data, key):
    assert menu.parse_key(data) == key


def test_age_text():
    assert menu.age_text(None) == "no scan yet"
    assert menu.age_text(0) == "today"
    assert menu.age_text(menu.DAY - 1) == "today"
    assert menu.age_text(menu.DAY) == "1 day ago"
    assert menu.age_text(2 * menu.DAY + 5) == "2 days ago"
    assert menu.age_text(1.5 * menu.DAY) == "1 day ago"


def test_render_matches_the_design_frame():
    assert "\n".join(menu.render(0, PLAIN, "0.2.0", "2 days ago")) == (
        "Constellation 0.2.0 · your Claude Code setup, mapped\n"
        "\n"
        "  ➤ 1  Analyze       what costs context, what is unused, what clashes\n"
        "    2  Doctor        one-screen health of your setup and this install\n"
        "    3  Clean         build a cleanup checklist (nothing is deleted)\n"
        "    4  Weekly        what changed since last week\n"
        "    5  Open map      the interactive graph in your browser\n"
        "    6  Update        check for a newer version\n"
        "\n"
        "  ↑↓ or 1-6 · Enter run · h help · q quit   last scan: 2 days ago"
    )


def test_render_marks_only_the_selected_row_and_bolds_it():
    lines = menu.render(2, Style(True, 80), "1", "today")
    assert lines[0].startswith("\033[1mConstellation 1\033[0m")
    assert [i for i, line in enumerate(lines) if "➤" in line] == [4]
    assert lines[4] == "  \033[1m➤ 3  Clean         build a cleanup checklist (nothing is deleted)\033[0m"
    assert sum("\033[" in line for line in lines) == 2


def test_plan():
    assert menu.plan(1, True, "C") == [["doctor"]]
    assert menu.plan(2, False, "C") == [["clean"]]
    assert menu.plan(3, True, "C") == [["weekly"]]
    assert menu.plan(4, True, "C") == [["open"]]
    assert menu.plan(5, True, "C") == [["update"]]
    assert menu.plan(0, True, "C") == [["doctor"], ["cost"], ["unused"]]
    assert menu.plan(0, False, "C") == [["scan", "C", "--offline"], ["doctor"], ["cost"], ["unused"]]


def test_scan_age(tmp_path: Path):
    f = tmp_path / "s.json"
    assert menu.scan_age(f, 100.0) is None
    f.write_text("{}")
    mtime = f.stat().st_mtime
    assert menu.scan_age(f, mtime + 50) == pytest.approx(50)
    assert menu.scan_age(f, mtime - 50) == 0.0


def test_numbered_fallback():
    prompts = []

    def answers(*items):
        it = iter(items)
        return lambda prompt: prompts.append(prompt) or next(it)

    out, seen = [], []

    def lines_for(i):
        seen.append(i)
        return ["l1", "l2"]

    assert menu.numbered(answers("zz", "9", "0", "enter", " 3 "), out.append, lines_for) == menu.Action("run", 2)
    assert out == ["l1\nl2\n"] and seen == [-1]
    assert prompts == ["number, h or q: "] * 5
    assert menu.numbered(answers("1"), out.append, lambda i: []) == menu.Action("run", 0)
    assert menu.numbered(answers("6"), out.append, lambda i: []) == menu.Action("run", 5)
    assert menu.numbered(answers("Q"), out.append, lambda i: []) == menu.Action("quit")
    assert menu.numbered(answers("h"), out.append, lambda i: []) == menu.Action("help")

    def eof(prompt):
        raise EOFError

    assert menu.numbered(eof, out.append, lambda i: []) == menu.Action("quit")


class FakeTermios:
    TCSADRAIN = 1

    def __init__(self):
        self.calls = []

    def tcgetattr(self, fd):
        self.calls.append(("get", fd))
        return "saved"

    def tcsetattr(self, fd, when, attrs):
        self.calls.append(("set", fd, when, attrs))


class FakeTty:
    def __init__(self, calls):
        self.calls = calls

    def setraw(self, fd):
        self.calls.append(("raw", fd))


def test_raw_mode_restores_on_exit_and_on_exception():
    t = FakeTermios()
    with menu.raw_mode(7, t, FakeTty(t.calls)):
        assert t.calls == [("get", 7), ("raw", 7)]
    assert t.calls[-1] == ("set", 7, 1, "saved")

    t = FakeTermios()
    with pytest.raises(KeyboardInterrupt), menu.raw_mode(7, t, FakeTty(t.calls)):
        raise KeyboardInterrupt
    assert t.calls[-1] == ("set", 7, 1, "saved")
    assert ("raw", 7) in t.calls


class Runner:
    def __init__(self, codes=None):
        self.calls = []
        self.codes = codes or {}

    def __call__(self, argv):
        self.calls.append(argv)
        return self.codes.get(argv[0], 0)


def launch(tmp_path, *keys, runner=None, answers=("y",), age=None, entered=None):
    runner = runner or Runner()
    tmp_path.mkdir(exist_ok=True)
    scan = tmp_path / "c.json"
    if age is not None:
        scan.write_text("{}")
    now = scan.stat().st_mtime + age if age is not None else 0.0
    asked = []
    it = iter(answers)

    def confirm(prompt):
        asked.append(prompt)
        return next(it)

    @contextlib.contextmanager
    def raw():
        if entered is not None:
            entered.append("in")
        try:
            yield
        finally:
            if entered is not None:
                entered.append("out")

    code = menu.launch(runner, scan, "/cfg", st=PLAIN, confirm=confirm, raw=raw, keys=keys_of(*keys), now=lambda: now)
    return code, runner.calls, asked


def test_launch_runs_the_chosen_subcommand_inside_raw_mode_only_for_the_menu(tmp_path, capsys):
    entered = []
    code, calls, asked = launch(tmp_path, "down", "enter", entered=entered)
    assert (code, calls, asked) == (0, [["doctor"]], [])
    assert entered == ["in", "out"]
    out = capsys.readouterr().out
    assert "last scan: no scan yet" in out
    assert "➤ 1  Analyze" in out


def test_launch_shows_scan_age(tmp_path, capsys, monkeypatch):
    asked = []
    real = menu.importlib.metadata.version
    monkeypatch.setattr(menu.importlib.metadata, "version", lambda name: asked.append(name) or real(name))
    launch(tmp_path, "q", age=2 * menu.DAY + 5)
    assert asked == ["constellation-cli"]
    out = capsys.readouterr().out
    assert f"Constellation {VERSION}" in out
    assert "last scan: 2 days ago" in out


def test_launch_quit_help_interrupt(tmp_path):
    assert launch(tmp_path, "q") == (0, [], [])
    assert launch(tmp_path, "h") == (0, [["--help"]], [])
    assert launch(tmp_path, "ctrl-c") == (130, [], [])


def test_analyze_with_fresh_scan_skips_scan_and_does_not_ask(tmp_path):
    assert launch(tmp_path, "enter", age=menu.DAY - 1) == (0, [["doctor"], ["cost"], ["unused"]], [])


def test_analyze_with_stale_or_missing_scan_asks_first(tmp_path):
    code, calls, asked = launch(tmp_path, "enter", age=menu.DAY)
    assert code == 0 and calls[0] == ["scan", "/cfg", "--offline"] and len(calls) == 4
    assert asked == ["No fresh scan. Run `constellation scan /cfg --offline` (reads /cfg locally, sends nothing)? [y/N] "]
    assert launch(tmp_path / "none", "enter")[1][0] == ["scan", "/cfg", "--offline"]


@pytest.mark.parametrize("answer", ["n", "", "yes please"])
def test_analyze_declined_runs_nothing(tmp_path, answer):
    assert launch(tmp_path, "enter", answers=(answer,))[:2] == (0, [])


def test_answer_is_case_and_space_insensitive(tmp_path):
    assert len(launch(tmp_path, "enter", answers=(" Y ",))[1]) == 4


def test_failure_stops_the_sequence_and_is_returned(tmp_path):
    code, calls, _ = launch(tmp_path, "enter", runner=Runner({"scan": 2}))
    assert (code, calls) == (2, [["scan", "/cfg", "--offline"]])
    code, calls, _ = launch(tmp_path, "enter", age=0, runner=Runner({"cost": 3}))
    assert (code, calls) == (3, [["doctor"], ["cost"]])


def test_launch_without_a_key_reader_uses_the_numbered_prompt(tmp_path):
    runner = Runner()
    answers = iter(["2"])
    code = menu.launch(runner, tmp_path / "x", "/cfg", st=PLAIN, confirm=lambda p: next(answers), keys=None)
    assert (code, runner.calls) == (0, [["doctor"]])


def test_default_config_dir_is_the_users_claude_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = Runner()
    menu.launch(runner, tmp_path / "x", None, st=PLAIN, confirm=lambda p: "y", keys=keys_of("enter"))
    assert runner.calls[0] == ["scan", str(tmp_path / ".claude"), "--offline"]


def fake_stdin(monkeypatch, *chunks):
    class Stdin:
        def fileno(self):
            return 9

    reads = []
    data = iter(chunks)
    monkeypatch.setattr(menu.sys, "stdin", Stdin())
    monkeypatch.setattr(menu.os, "read", lambda fd, n: reads.append((fd, n)) or next(data))
    return reads


def test_terminal_streams_keys_from_stdin_including_unknown_ones(monkeypatch):
    reads = fake_stdin(monkeypatch, b"\x1b[C", b"\x1b[B")
    term = menu.terminal()
    assert term is not None
    keys = iter(term[1])
    assert [next(keys), next(keys)] == ["", "down"]
    assert reads == [(9, 8), (9, 8)]


def test_terminal_raw_context_uses_the_real_fd_and_modules(monkeypatch):
    fake_stdin(monkeypatch)
    t = FakeTermios()
    monkeypatch.setitem(menu.sys.modules, "termios", t)
    monkeypatch.setitem(menu.sys.modules, "tty", FakeTty(t.calls))
    term = menu.terminal()
    assert term is not None
    with term[0]():
        pass
    assert t.calls == [("get", 9), ("raw", 9), ("set", 9, 1, "saved")]


def test_terminal_is_none_without_termios(monkeypatch):
    monkeypatch.setitem(menu.sys.modules, "termios", None)
    assert menu.terminal() is None


def test_open_menu_ctrl_c_exits_130(monkeypatch):
    monkeypatch.setattr(menu, "terminal", lambda: None)

    def boom(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(menu, "launch", boom)
    assert menu.open_menu(Runner()) == 130


def test_open_menu_passes_the_terminal_hooks(monkeypatch):
    seen = {}
    runner = Runner()
    monkeypatch.setattr(menu, "terminal", lambda: ("RAW", "KEYS"))
    monkeypatch.setattr(menu, "launch", lambda run, **k: seen.update(k, run=run) or 7)
    assert menu.open_menu(runner) == 7
    assert (seen["raw"], seen["keys"], seen["run"]) == ("RAW", "KEYS", runner)
    assert isinstance(seen["st"], Style)
    monkeypatch.setattr(menu, "terminal", lambda: None)
    menu.open_menu(runner)
    assert (seen["raw"], seen["keys"]) == (None, None)


class Tty:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


def test_main_without_args_opens_the_menu_only_on_a_tty(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(menu, "open_menu", lambda run: opened.append(run) or 0)
    monkeypatch.setattr(cli.sys, "stdin", Tty(True))
    monkeypatch.setattr(cli.sys, "stdout", Tty(True))
    assert cli.main([]) == 0
    assert opened == [cli.main]
    for stdin, stdout in [(False, True), (True, False)]:
        opened.clear()
        monkeypatch.setattr(cli.sys, "stdin", Tty(stdin))
        monkeypatch.setattr(cli.sys, "stdout", Tty(stdout))
        with pytest.raises(SystemExit):
            cli.main([])
        assert opened == []
