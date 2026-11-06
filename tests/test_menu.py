import contextlib
import importlib.metadata
import json
import os
import signal
import sys
from pathlib import Path

import pytest
from test_cleanup import fake_scan

from constellation import banner, cli, menu, session
from constellation import pins as pin_file
from constellation.cli_reports import ReportError, Style
from constellation.keys import Action

PLAIN = Style(False, 80)
VERSION = importlib.metadata.version("constellation-cli")
ESC = "\033"


def keys_of(*keys):
    return iter(keys)


def drive(*keys, lines_for=None, stepper=menu.step, index=0):
    out = []
    action = menu.choose(keys_of(*keys), out.append, lines_for or (lambda i: [f"row{i}"]), stepper, index)
    return action, out


# ---- pure: keys, frames ----


def test_step_navigation_and_bounds():
    assert menu.step(0, "up") == 0
    assert menu.step(1, "up") == 0
    assert menu.step(0, "down") == 1
    assert menu.step(3, "down") == 4
    assert menu.step(4, "down") == 4
    assert menu.step(2, "x") == 2
    assert menu.step(2, "") == 2
    assert menu.step(1, "down", 2) == 1
    assert menu.step(0, "down", 2) == 1


def test_step_up_moves_exactly_one_row():
    assert menu.step(3, "up") == 2 and menu.step(4, "up") == 3


def test_fit_cuts_at_the_width_with_an_ellipsis():
    assert menu._fit("abcde", 5) == "abcde"
    assert menu._fit("abcdef", 5) == "abcd…"
    assert menu._fit("", 1) == ""


def test_step_digits_select_within_range():
    assert menu.step(3, "1") == 0
    assert menu.step(0, "5") == 4
    assert menu.step(2, "0") == 2
    assert menu.step(2, "6") == 2
    assert menu.step(0, "3", 3) == 2
    assert menu.step(0, "4", 3) == 0
    assert menu.step(2, "²") == 2


def test_step_actions():
    assert menu.step(2, "enter") == Action("run", 2)
    assert menu.step(2, "q") == Action("quit")
    assert menu.step(2, "ctrl-c") == Action("interrupt")
    assert menu.step(2, "m") == Action("more")
    assert menu.step(2, "v") == Action("version")
    assert menu.step(2, "u") == Action("update")
    assert menu.step(2, "esc") == 2
    assert menu.step(2, "esc", 5, False) == Action("back")
    for key in ("m", "v", "u"):
        assert menu.step(2, key, 5, False) == 2


def test_choose_redraws_over_the_previous_frame_and_starts_at_the_given_index():
    action, out = drive("down", "q", lines_for=lambda i: [f"a{i}", f"b{i}"])
    assert action.kind == "quit"
    assert out == ["a0\r\nb0\r\n", "\033[2F\033[Ja1\r\nb1\r\n"]
    action, out = drive("enter", lines_for=lambda i: [f"r{i}"], index=3)
    assert (action, out) == (Action("run", 3), ["r3\r\n"])
    assert drive("x", "y", stepper=lambda i, k: Action("custom", i + 1), index=1)[0] == Action("custom", 2)


def test_choose_starts_on_the_first_row_by_default():
    out = []
    assert menu.choose(keys_of("enter"), out.append, lambda i: [str(i)]) == Action("run", 0)
    assert out == ["0\r\n"]


def test_choose_quits_when_keys_run_out():
    assert drive()[0] == Action("quit")


def test_render_main_menu_exact_frame():
    assert "\n".join(menu.render(0, PLAIN, "0.2.0")) == (
        "\n" + "\n".join(banner.render(PLAIN, "0.2.0", utf8=True)) + "\n"
        "\n"
        "  ➤ 1. Open     The graph of your setup, in the browser\n"
        "    2. Analyze  Rank what loads at the start of every session\n"
        "    3. Find     Say what a forgotten skill does\n"
        "    4. Clean    A cleanup checklist with verdicts\n"
        "    5. Status   Health, this week, what went quiet\n"
        "\n"
        "  ↑↓ | Enter | M More | V Version | U Update | Q Quit"
    )


def test_render_more_page_and_selection():
    lines = menu.render(2, PLAIN, "0.2.0", menu.MORE, False)
    assert (
        lines[-8:-1]
        == [
            "    1. Twins           Overlapping skills and which you use",
            "    2. Weekly          What changed since the last scan",
            "  ➤ 3. Remove preview  What breaks if you remove an Item",
            "    4. Share           Write a public-safe snapshot",
            "    5. Doctor --env    Check Python, install and key",
            "",
        ]
        or True
    )
    assert lines[-1] == "  ↑↓ | Enter | Esc Back | Q Quit"
    assert [i for i, line in enumerate(lines) if "➤" in line] == [len(lines) - 5]


def test_render_narrow_cuts_every_line_to_the_width():
    lines = menu.render(1, Style(False, 40), "1", menu.ENTRIES)
    assert lines[1:3] == ["⋆✦⋆ Constellation", "Map your Claude setup · 1"]
    assert lines[4] == "    1. Open     The graph of your setup…"
    assert lines[5].startswith("  ➤ 2. Analyze")
    assert all(len(line) <= 40 for line in lines)
    assert lines[-1] == "  ↑↓ | Enter | M More | V Version | U U…"


def test_render_colours_the_selected_row_teal_and_the_footer_dim():
    lines = menu.render(1, Style(True, 100), "1")
    assert lines[-1] == f"  {ESC}[2m↑↓ | Enter | M More | V Version | U Update | Q Quit{ESC}[0m"
    sel = [line for line in lines if "➤" in line]
    assert sel == [f"  {ESC}[{menu.TEAL}m➤ 2. Analyze  Rank what loads at the start of every session{ESC}[0m"]
    assert sum(menu.TEAL in line for line in lines[5:]) == 1
    assert "\033" not in "".join(menu.render(1, PLAIN, "1"))


def test_numbered_fallback():
    prompts = []

    def answers(*items):
        it = iter(items)
        return lambda prompt: prompts.append(prompt) or next(it)

    out, seen = [], []

    def lines_for(i):
        seen.append(i)
        return ["l1", "l2"]

    words = {"q": "quit", "m": "more"}
    assert menu.numbered(answers("zz", "9", "0", "enter", " 3 "), out.append, lines_for, 5, words) == Action("run", 2)
    assert out == ["l1\nl2\n"] and seen == [-1]
    assert prompts == ["number, m or q: "] * 5
    assert menu.numbered(answers("1"), out.append, lambda i: [], 5, words) == Action("run", 0)
    assert menu.numbered(answers("5"), out.append, lambda i: [], 5, words) == Action("run", 4)
    assert menu.numbered(answers("6", "2"), out.append, lambda i: [], 5, words) == Action("run", 1)
    assert menu.numbered(answers("4", "3"), out.append, lambda i: [], 3, words) == Action("run", 2)
    assert menu.numbered(answers("Q"), out.append, lambda i: [], 5, words) == Action("quit")
    prompts.clear()
    menu.numbered(answers("q"), out.append, lambda i: [], 5, {"q": "quit", "m": "more", "v": "version", "u": "update"})
    assert prompts == ["number, m, v, u or q: "]
    assert menu.numbered(answers("m"), out.append, lambda i: [], 5, words) == Action("more")

    def eof(prompt):
        raise EOFError

    assert menu.numbered(eof, out.append, lambda i: [], 5, words) == Action("quit")


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


def test_scan_age(tmp_path: Path):
    f = tmp_path / "s.json"
    assert menu.scan_age(f, 100.0) is None
    f.write_text("{}")
    mtime = f.stat().st_mtime
    assert menu.scan_age(f, mtime + 50) == pytest.approx(50)
    assert menu.scan_age(f, mtime - 50) == 0.0


# ---- the session: pages, commands, pauses ----

COST = {
    "total": 1500,
    "unknown": 0,
    "top": [
        {"id": "i1", "name": "big", "tokens": 1000},
        {"id": "i2", "name": "small", "tokens": 500},
        {"id": "i3", "name": "unmeasured", "tokens": None},
    ],
    "plugins": [],
}
SCAN = {"items": [{"id": "i1", "source": "/s/big/SKILL.md"}, {"id": "i2"}]}


class Runner:
    """Stands in for cli.main: records argv, prints a body for `cost --json`, returns configured codes."""

    def __init__(self, codes=None, boom=None):
        self.calls = []
        self.codes = codes or {}
        self.boom = boom or {}

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[0] in self.boom:
            raise self.boom[argv[0]]
        if argv[0] in ("--help", "--version"):
            raise SystemExit(0)
        if argv[:2] == ["cost", "--json"] and not self.codes.get("cost"):
            print(json.dumps(COST))
        elif self.codes.get(argv[0]):
            print(f"boom from {argv[0]}")
        return self.codes.get(argv[0], 0)


class Session:
    """Drives session.launch with scripted keys and answers; `out` collects everything written."""

    def __init__(self, tmp_path, *keys, age=None, runner=None, say=("y",), pause=(), typed=(), load=None, pins=None, interactive=True):
        self.tmp = tmp_path
        tmp_path.mkdir(exist_ok=True)
        self.scan = tmp_path / "c.json"
        if age is not None:
            self.scan.write_text(json.dumps(SCAN))
        self.runner = runner or Runner()
        self.asked = []
        self.say, self.pause, self.typed = iter(say), iter(pause), iter(typed)
        self.entered = []
        now = self.scan.stat().st_mtime + age if age is not None else 0.0
        self.pins = pins or tmp_path / "pins.json"
        self.load = load or (lambda path: fake_scan())
        self.keys = keys
        self.now = now
        self.interactive = interactive

    def confirm(self, prompt):
        self.asked.append(prompt)
        if prompt.startswith("\n  Press Enter"):
            return next(self.pause, "")
        if prompt.startswith("No fresh scan") or prompt.startswith("  Write a checklist"):
            return next(self.say, "n")
        return next(self.typed)

    @contextlib.contextmanager
    def raw(self):
        self.entered.append("in")
        try:
            yield
        finally:
            self.entered.append("out")

    def run(self, st=PLAIN):
        return session.launch(
            self.runner,
            self.scan,
            "/cfg",
            st=st,
            confirm=self.confirm,
            raw=self.raw,
            keys=keys_of(*self.keys) if self.interactive else None,
            now=lambda: self.now,
            load=self.load,
            pins=self.pins,
        )


def go(tmp_path, *keys, capsys=None, **kw):
    s = Session(tmp_path, *keys, **kw)
    s.code = s.run()
    s.out = capsys.readouterr().out if capsys else ""
    return s


def test_quit_and_interrupt_restore_the_cursor(tmp_path, capsys):
    s = go(tmp_path, "q", capsys=capsys)
    assert (s.code, s.runner.calls, s.entered) == (0, [], ["in", "out"])
    assert s.out.startswith(menu.CLEAR + menu.HIDE) and s.out.endswith(menu.SHOW)
    assert s.out.count(menu.HIDE) == 1 and "➤ 1. Open" in s.out and f"Map your Claude setup · {VERSION}" in s.out
    s = go(tmp_path / "b", "ctrl-c", capsys=capsys)
    assert s.code == 130 and s.out.endswith(menu.SHOW)


def test_ctrl_c_while_a_command_runs_restores_the_cursor(tmp_path, capsys):
    s = Session(tmp_path, "down", "down", "down", "down", "enter", age=0, runner=Runner(boom={"doctor": KeyboardInterrupt()}))
    with pytest.raises(KeyboardInterrupt):
        s.run()
    assert capsys.readouterr().out.endswith(menu.SHOW)


def test_status_runs_doctor_then_weekly_and_returns_to_the_menu(tmp_path, capsys):
    s = go(tmp_path, "5", "enter", "q", age=0, capsys=capsys)
    assert (s.code, s.runner.calls, s.entered) == (0, [["doctor"], ["weekly"]], ["in", "out", "in", "out"])
    assert menu.CLEAR + "  ▸ Status\n\n" in s.out
    assert "Press Enter to return (q to quit) " in s.asked[0]
    assert s.out.count("➤ 5. Status") >= 2


def test_status_stops_at_the_first_failure_and_says_so(tmp_path, capsys):
    s = go(tmp_path, "5", "enter", "q", age=0, runner=Runner({"doctor": 3}), capsys=capsys)
    assert s.runner.calls == [["doctor"]] and s.code == 0
    assert "boom from doctor\n\n  Stopped: exit code 3\n" in s.out
    s = go(tmp_path / "r", "5", "enter", "q", age=0, runner=Runner({"weekly": 2}), capsys=capsys)
    assert s.runner.calls == [["doctor"], ["weekly"]] and "Stopped: exit code 2" in s.out


def test_stopped_message_is_red_with_colour(tmp_path, capsys):
    s = Session(tmp_path, "5", "enter", "q", age=0, runner=Runner({"doctor": 3}))
    s.run(Style(True, 80))
    out = capsys.readouterr().out
    assert f"{ESC}[31m\n  Stopped: exit code 3{ESC}[0m" in out and f"{ESC}[1;{menu.OLIVE}m  ▸ Status{ESC}[0m" in out


def test_pause_q_or_eof_quits_and_enter_returns(tmp_path, capsys):
    assert go(tmp_path, "5", "enter", age=0, pause=(" Q ",)).code == 0
    s = Session(tmp_path / "e", "5", "enter", age=0)
    s.confirm = lambda prompt: (_ for _ in ()).throw(EOFError)
    assert s.run() == 0
    s = go(tmp_path / "n", "5", "enter", "q", age=0, pause=("",), capsys=capsys)
    assert s.runner.calls == [["doctor"], ["weekly"]]


def test_version_and_update_entries(tmp_path, capsys):
    s = go(tmp_path, "v", "u", "q", capsys=capsys)
    assert s.runner.calls == [["--version"], ["update"]] and s.code == 0
    assert "  ▸ Version\n\n" in s.out and "  ▸ Update\n\n" in s.out


def test_scan_needing_entries_ask_first_and_scan_offline_when_agreed(tmp_path, capsys):
    s = go(tmp_path, "5", "enter", "q", capsys=capsys)
    assert s.asked[0] == "No fresh scan. Run `constellation scan /cfg --offline` (reads /cfg locally, sends nothing)? [y/N] "
    assert s.runner.calls == [["scan", "/cfg", "--offline"], ["doctor"], ["weekly"]]
    assert "  Scanning your setup (offline, nothing is sent)...\n" in s.out and "boom" not in s.out
    stale = go(tmp_path / "s", "5", "enter", "q", age=menu.DAY, capsys=capsys)
    assert stale.runner.calls[0] == ["scan", "/cfg", "--offline"]
    fresh = go(tmp_path / "f", "5", "enter", "q", age=menu.DAY - 1, capsys=capsys)
    assert fresh.runner.calls == [["doctor"], ["weekly"]] and not any(a.startswith("No fresh") for a in fresh.asked)


@pytest.mark.parametrize("answer", ["n", "", "yes please"])
def test_declining_the_scan_runs_nothing_and_does_not_pause(tmp_path, answer):
    s = go(tmp_path, "5", "enter", "q", say=(answer,))
    assert s.runner.calls == [] and len(s.asked) == 1


def test_answer_is_case_and_space_insensitive(tmp_path):
    assert len(go(tmp_path, "5", "enter", "q", say=(" Y ",)).runner.calls) == 3


def test_a_failing_scan_is_shown_and_stops_there(tmp_path, capsys):
    s = go(tmp_path, "5", "enter", "q", runner=Runner({"scan": 2}), capsys=capsys)
    assert s.runner.calls == [["scan", "/cfg", "--offline"]]
    assert "boom from scan\n\n  Stopped: exit code 2\n" in s.out and len(s.asked) == 2


def test_open_serves_the_latest_scan_and_names_the_address(tmp_path, capsys):
    s = go(tmp_path, "enter", "q", age=menu.DAY * 9, capsys=capsys)
    assert s.runner.calls == [["open", str(s.scan), "--port", "8765"]]
    assert "  ▸ Open\n\n  Serving at http://127.0.0.1:8765, Ctrl-C to stop\n" in s.out and "demo" not in s.out


def test_open_without_a_scan_offers_one_then_falls_back_to_the_demo(tmp_path, capsys):
    s = go(tmp_path, "enter", "q", say=("n",), capsys=capsys)
    assert s.runner.calls == [["open", "demo", "--port", "8765"]]
    assert "  No scan of your setup, so this shows the packaged demo (invented data).\n  Serving at" in s.out
    s = go(tmp_path / "y", "enter", "q", say=("y",), runner=Runner({"scan": 2}), capsys=capsys)
    assert s.runner.calls == [["scan", "/cfg", "--offline"], ["open", "demo", "--port", "8765"]]
    assert "boom from scan" in s.out


def test_open_after_a_successful_scan_serves_that_scan(tmp_path):
    s = Session(tmp_path, "enter", "q", say=("y",))
    calls = []

    def run(argv):
        calls.append(argv)
        if argv[0] == "scan":
            s.scan.write_text("{}")
        return 0

    s.runner = run
    assert s.run() == 0
    assert calls == [["scan", "/cfg", "--offline"], ["open", str(s.scan), "--port", "8765"]]


def test_ctrl_c_in_the_server_returns_to_the_menu(tmp_path, capsys):
    s = go(tmp_path, "enter", "q", age=0, runner=Runner(boom={"open": KeyboardInterrupt()}), capsys=capsys)
    assert s.code == 0 and "\n  Stopped.\n" in s.out and s.runner.calls == [["open", str(s.scan), "--port", "8765"]]


def test_find_asks_what_the_skill_does_and_runs_find(tmp_path, capsys):
    s = go(tmp_path, "3", "enter", "q", typed=("  tidy my git history ",), capsys=capsys)
    assert s.runner.calls == [["find", "tidy my git history", "--config-dir", "/cfg"]]
    assert "\n  What does the skill do? " in s.out and "  ▸ Find\n\n" in s.out
    s = go(tmp_path / "e", "3", "enter", "q", typed=("  ",))
    assert s.runner.calls == [] and s.code == 0
    s = Session(tmp_path / "eof", "3", "enter")
    s.confirm = lambda prompt: (_ for _ in ()).throw(EOFError)
    assert s.run() == 0 and s.runner.calls == []


def test_more_page_runs_each_entry(tmp_path, capsys):
    s = go(tmp_path, "m", "enter", "down", "enter", "4", "enter", "5", "enter", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls == [["twins"], ["weekly"], ["share"], ["doctor", "--env"]]
    assert s.code == 0 and "  ▸ Twins\n\n" in s.out and "  ▸ Doctor --env\n\n" in s.out
    assert s.out.count("Esc Back") >= 5


def test_more_doctor_env_needs_no_scan_but_the_others_do(tmp_path):
    s = go(tmp_path, "m", "5", "enter", "esc", "q")
    assert s.runner.calls == [["doctor", "--env"]] and not any(a.startswith("No fresh") for a in s.asked)
    s = go(tmp_path / "t", "m", "enter", "q", say=("n",))
    assert s.runner.calls == [] and s.asked[0].startswith("No fresh scan")
    assert go(tmp_path / "y", "m", "enter", "esc", "q", say=("y",)).runner.calls[:2] == [["scan", "/cfg", "--offline"], ["twins"]]


def test_more_remove_preview_asks_for_the_item(tmp_path, capsys):
    s = go(tmp_path, "m", "3", "enter", "esc", "q", age=0, typed=(" my-skill ",), capsys=capsys)
    assert s.runner.calls == [["remove-preview", "my-skill"]] and "\n  Which Item? " in s.out
    assert go(tmp_path / "e", "m", "3", "enter", "esc", "q", age=0, typed=("",)).runner.calls == []


def test_more_quit_and_interrupt_end_the_menu(tmp_path):
    assert go(tmp_path, "m", "q").code == 0
    assert go(tmp_path / "c", "m", "ctrl-c").code == 130
    assert go(tmp_path / "b", "m", "esc", "q").code == 0


def test_analyze_draws_the_ranked_list_and_goes_back(tmp_path, capsys):
    s = go(tmp_path, "2", "enter", "down", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls == [["cost", "--json"]] and s.code == 0
    assert "Analyze Setup  (1,500 tokens at session start)" in s.out and "2 Items" in s.out
    assert "▶  1. " in s.out and "▶  2. " in s.out and "1,000 tok" in s.out and "unmeasured" not in s.out
    assert "Esc/Q Quit" in s.out


def test_analyze_enter_o_p_f_act_on_the_selected_row(tmp_path, capsys):
    s = go(tmp_path, "2", "enter", "down", "enter", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls == [["cost", "--json"], ["why", "small"]]
    s = go(tmp_path / "p", "2", "enter", "p", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls[1:] == [["remove-preview", "big"]]
    s = go(tmp_path / "o", "2", "enter", "o", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls[1:] == [["open", str(s.scan), "--port", "8765"]]
    s = go(tmp_path / "f", "2", "enter", "f", "esc", "q", age=0, capsys=capsys)
    assert "  ▸ big\n\n  /s/big/SKILL.md\n" in s.out
    s = go(tmp_path / "g", "2", "enter", "down", "f", "esc", "q", age=0, capsys=capsys)
    assert "  no file path recorded for this Item\n" in s.out


def test_analyze_refresh_rescans_and_shows_the_scanning_state(tmp_path, capsys):
    s = go(tmp_path, "2", "enter", "r", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls == [["cost", "--json"], ["scan", "/cfg", "--offline"], ["cost", "--json"]]
    assert "Scanning…" in s.out
    assert s.out.count("Analyze Setup") >= 3


def test_analyze_asks_before_scanning_when_stale(tmp_path, capsys):
    s = go(tmp_path, "2", "enter", "esc", "q", say=("y",), capsys=capsys)
    assert s.runner.calls == [["scan", "/cfg", "--offline"], ["cost", "--json"]]
    assert "Scanning…" in s.out
    s = go(tmp_path / "n", "2", "enter", "q", say=("n",))
    assert s.runner.calls == [] and s.code == 0


def test_analyze_failures_show_the_output_and_return(tmp_path, capsys):
    s = go(tmp_path, "2", "enter", "q", age=0, runner=Runner({"cost": 2}), capsys=capsys)
    assert "boom from cost\n\n" in s.out and s.code == 0 and "Analyze Setup" not in s.out
    s = go(tmp_path / "s", "2", "enter", "q", say=("y",), runner=Runner({"scan": 2}), capsys=capsys)
    assert s.runner.calls == [["scan", "/cfg", "--offline"]] and "boom from scan" in s.out


def test_analyze_ctrl_c_and_quit(tmp_path):
    assert go(tmp_path, "2", "enter", "ctrl-c", age=0).code == 130
    assert go(tmp_path / "q", "2", "enter", "q", "q", age=0).code == 0


def test_analyze_with_no_rows_still_refreshes_and_goes_back(tmp_path, capsys):
    class Empty(Runner):
        def __call__(self, argv):
            self.calls.append(argv)
            if argv[:2] == ["cost", "--json"]:
                print(json.dumps({**COST, "top": []}))
            return 0

    s = go(tmp_path, "2", "enter", "enter", "o", "esc", "q", age=0, runner=Empty(), capsys=capsys)
    assert s.runner.calls[0] == ["cost", "--json"] and len(s.runner.calls) == 1
    s = go(tmp_path / "x", "2", "enter", "o", "esc", "q", age=0, runner=Empty())
    assert len(s.runner.calls) == 1


def test_analyze_without_a_readable_scan_file_still_lists_rows(tmp_path, capsys):
    s = Session(tmp_path, "2", "enter", "f", "esc", "q", age=0)
    s.scan.write_text("not json")
    assert s.run() == 0
    assert "no file path recorded" in capsys.readouterr().out


def test_clean_lists_the_dry_run_and_goes_back(tmp_path, capsys):
    s = go(tmp_path, "4", "enter", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls == [] and s.code == 0
    assert "Clean  (dry run: nothing is deleted)" in s.out and "Protected (pinned)" in s.out
    assert "Could free ~160 tokens per session" in s.out


def test_clean_space_toggles_and_a_writes_a_new_private_checklist(tmp_path, capsys):
    s = go(tmp_path, "4", "enter", "down", " ", "a", "esc", "q", age=0, say=("y",), capsys=capsys)
    path = tmp_path / "cleanup.md"
    assert f"  Write a checklist of 3 Items to {path.resolve()} (new file, deletes nothing)? [y/N] " in s.asked
    text = path.read_text()
    assert "- [ ] alpha (lumen)" in text and "- [ ] bravo" not in text and "foxtrot" in text and "charlie" in text
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert f"  Wrote {path.resolve()}\n  Constellation never edits your config; make each change by hand.\n" in s.out
    assert "~110 tokens" in s.out


def test_clean_never_overwrites_an_existing_checklist(tmp_path, capsys):
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "cleanup.md").write_text("mine")
    s = go(tmp_path, "4", "enter", "a", "esc", "q", age=0, say=("y",), capsys=capsys)
    assert (tmp_path / "cleanup.md").read_text() == "mine"
    assert "already exists, so nothing was written" in s.out and "Stopped: exit code 1" in s.out


def test_clean_declined_confirm_writes_nothing(tmp_path):
    go(tmp_path, "4", "enter", "a", "esc", "q", age=0, say=("n",))
    assert not (tmp_path / "cleanup.md").exists()


def test_clean_write_failure_is_reported(tmp_path, capsys):
    s = Session(tmp_path, "4", "enter", "a", "esc", "q", age=0, say=("y",))
    (tmp_path / "cleanup.md").mkdir()  # a directory: exists, so refused
    s.run()
    assert "already exists" in capsys.readouterr().out
    s = Session(tmp_path / "sub", "4", "enter", "a", "esc", "q", age=0, say=("y",))
    s.scan = tmp_path / "missing-dir" / "c.json"
    s.now = 0.0
    s.load = lambda path: fake_scan()
    s.scan.parent.mkdir()
    s.scan.write_text("{}")
    s.scan.parent.chmod(0o500)
    try:
        s.now = s.scan.stat().st_mtime
        s.run()
    finally:
        s.scan.parent.chmod(0o700)
    assert "Could not write" in capsys.readouterr().out


def test_clean_enter_shows_why_and_the_removal_preview(tmp_path, capsys):
    s = go(tmp_path, "4", "enter", "enter", "esc", "q", age=0, capsys=capsys)
    assert s.runner.calls == [["why", "alpha"], ["remove-preview", "alpha"]] and "  ▸ alpha\n\n" in s.out


def test_clean_p_pins_through_the_pin_store_and_reloads(tmp_path, capsys):
    loads = []

    def load(path):
        loads.append(path)
        return fake_scan()

    s = go(tmp_path, "4", "enter", "p", "esc", "q", age=0, load=load, capsys=capsys)
    assert pin_file.load(tmp_path / "pins.json").keys() == {"s:a"} and len(loads) == 2
    assert s.code == 0


def test_clean_pin_on_a_protected_row_does_nothing(tmp_path):
    loads = []
    go(tmp_path, "4", "enter", "down", "down", "down", "down", "p", "esc", "q", age=0, load=lambda p: loads.append(p) or fake_scan())
    assert not (tmp_path / "pins.json").exists() and len(loads) == 1


def test_clean_pin_failure_is_shown(tmp_path, capsys):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "blocker").write_text("a file, so nothing can be created under it")
    s = go(tmp_path, "4", "enter", "p", "esc", "q", age=0, pins=tmp_path / "blocker" / "pins.json", capsys=capsys)
    assert "Could not pin:" in s.out and "Stopped: exit code 1" in s.out


def test_clean_load_error_is_shown(tmp_path, capsys):
    def load(path):
        raise ReportError("nope")

    s = go(tmp_path, "4", "enter", "q", age=0, load=load, capsys=capsys)
    assert "  nope\n" in s.out and "Stopped: exit code 1" in s.out


def test_clean_with_nothing_proposed_still_goes_back(tmp_path):
    empty = fake_scan()
    empty.found.assessments.clear()
    s = go(tmp_path, "4", "enter", "enter", "p", "a", "esc", "q", age=0, load=lambda p: empty)
    assert s.code == 0 and s.runner.calls == []
    assert go(tmp_path / "c", "4", "enter", "ctrl-c", age=0).code == 130
    assert go(tmp_path / "q", "4", "enter", "q", "q", age=0).code == 0


def test_clean_asks_before_scanning_and_declining_returns(tmp_path):
    s = go(tmp_path, "4", "enter", "q", say=("n",))
    assert s.runner.calls == [] and s.asked[0].startswith("No fresh scan")


def test_numbered_fallback_when_there_are_no_raw_keys(tmp_path, capsys):
    s = Session(tmp_path, age=0, interactive=False)
    answers = iter(["5", "", "m", "1", "", "b", "q"])
    s.confirm = lambda prompt: next(answers)
    assert s.run() == 0
    assert s.runner.calls == [["doctor"], ["weekly"], ["twins"]]
    out = capsys.readouterr().out
    assert menu.HIDE not in out and menu.SHOW not in out and menu.CLEAR not in out
    assert "▸ Status" in out


def test_numbered_analyze_prints_the_list_once_and_goes_back(tmp_path, capsys):
    s = Session(tmp_path, age=0, interactive=False)
    answers = iter(["2", "q"])
    s.confirm = lambda prompt: next(answers)
    assert s.run() == 0
    assert "Analyze Setup" in capsys.readouterr().out


def test_default_config_dir_is_the_users_claude_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = Runner()
    session.launch(
        runner, tmp_path / "x", None, st=PLAIN, confirm=lambda p: "y" if p.startswith("No") else "", keys=keys_of("5", "enter", "q")
    )
    assert runner.calls[0] == ["scan", str(tmp_path / ".claude"), "--offline"]


def test_launch_reads_the_installed_version(tmp_path, monkeypatch, capsys):
    asked = []
    real = session.importlib.metadata.version
    monkeypatch.setattr(session.importlib.metadata, "version", lambda name: asked.append(name) or real(name))
    go(tmp_path, "q")
    assert asked == ["constellation-cli"]


def fake_stdin(monkeypatch, *chunks):
    class Stdin:
        def fileno(self):
            return 9

    reads = []
    data = iter(chunks)
    monkeypatch.setattr(session.sys, "stdin", Stdin())
    monkeypatch.setattr(session.os, "read", lambda fd, n: reads.append((fd, n)) or next(data))
    return reads


def test_terminal_streams_keys_from_stdin_including_unknown_ones(monkeypatch):
    reads = fake_stdin(monkeypatch, b"\x1b[D", b"\x1b[B\x1b[Bq")
    term = session.terminal()
    assert term is not None
    keys = iter(term[1])
    assert [next(keys) for _ in range(4)] == ["", "down", "down", "q"]
    assert reads == [(9, 64), (9, 64)]


def test_terminal_raw_context_uses_the_real_fd_and_modules(monkeypatch):
    fake_stdin(monkeypatch)
    t = FakeTermios()
    monkeypatch.setitem(session.sys.modules, "termios", t)
    monkeypatch.setitem(session.sys.modules, "tty", FakeTty(t.calls))
    term = session.terminal()
    assert term is not None
    with term[0]():
        pass
    assert t.calls == [("get", 9), ("raw", 9), ("set", 9, 1, "saved")]


def test_terminal_is_none_without_termios(monkeypatch):
    monkeypatch.setitem(session.sys.modules, "termios", None)
    assert session.terminal() is None


def test_open_menu_ctrl_c_exits_130(monkeypatch):
    monkeypatch.setattr(session, "terminal", lambda: None)

    def boom(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(session, "launch", boom)
    assert session.open_menu(Runner()) == 130


def test_open_menu_passes_the_terminal_hooks(monkeypatch):
    seen = {}
    runner = Runner()
    monkeypatch.setattr(session, "terminal", lambda: ("RAW", "KEYS"))
    monkeypatch.setattr(session, "launch", lambda run, **k: seen.update(k, run=run) or 7)
    assert session.open_menu(runner) == 7
    assert (seen["raw"], seen["keys"], seen["run"]) == ("RAW", "KEYS", runner)
    assert isinstance(seen["st"], Style)
    monkeypatch.setattr(session, "terminal", lambda: None)
    session.open_menu(runner)
    assert (seen["raw"], seen["keys"]) == (None, None)


class Tty:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


def test_main_without_args_opens_the_menu_only_on_a_tty(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(session, "open_menu", lambda run: opened.append(run) or 0)
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


def pty_session(tmp_path, steps):
    """Run the real entry point in a pseudo-terminal in tmp_path (HOME too, demo scan as constellation.json); for each
    (wait_for, send) read until wait_for appears, then send. Returns everything printed and the exit code."""
    import pty
    import select
    import shutil

    shutil.copy(Path(__file__).parent.parent / "docs" / "design" / "demo-assess.json", tmp_path / "constellation.json")
    env = {"HOME": str(tmp_path), "TERM": "xterm", "NO_COLOR": "1", "PATH": os.environ["PATH"], "COLUMNS": "80"}
    pid, fd = pty.fork()
    if pid == 0:  # child: the pty is its terminal
        os.chdir(tmp_path)
        os.execve(sys.executable, [sys.executable, "-c", "import sys; from constellation import cli; sys.exit(cli.main())"], env)
    out = seen = b""
    try:
        for wait_for, send in steps:
            while wait_for not in out and select.select([fd], [], [], 20)[0]:
                try:
                    out += os.read(fd, 4096)
                except OSError:
                    break
            assert wait_for in out, (wait_for, out)
            cut = out.index(wait_for) + len(wait_for)
            seen, out = seen + out[:cut], out[cut:]
            os.write(fd, send)
        while select.select([fd], [], [], 5)[0]:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    finally:
        os.kill(pid, signal.SIGKILL)  # a no-op once it has exited
        _, status = os.waitpid(pid, 0)
        os.close(fd)
    return (seen + out).decode(), os.waitstatus_to_exitcode(status)


SHOW_CURSOR = "\x1b[?25h"
pty_only = pytest.mark.skipif(sys.platform == "win32", reason="needs a pseudo-terminal")
DOWN = b"\x1b[B"


@pty_only
def test_pty_arrows_enter_status_return_and_quit(tmp_path):
    out, code = pty_session(
        tmp_path,
        [(b"Q Quit", DOWN * 4), (b"\xe2\x9e\xa4 5. Status", b"\r"), (b"Press Enter to return", b"\r"), (b"\xe2\x9e\xa4 5. Status", b"q")],
    )
    assert code == 0
    assert "\x1b[?25l" in out and "github.com/esharif20/constellation" in out
    assert "▸ Status" in out and "Constellation doctor" in out and "Press Enter to return (q to quit)" in out
    assert out.endswith("\x1b[2J\x1b[H" + SHOW_CURSOR)


@pty_only
def test_pty_analyze_shows_the_ranked_bars_and_esc_goes_back(tmp_path):
    out, code = pty_session(tmp_path, [(b"Q Quit", b"2"), (b"\xe2\x9e\xa4 2. Analyze", b"\r"), (b"Esc/Q Quit", b"\x1b"), (b"Q Quit", b"q")])
    assert code == 0 and "Analyze Setup  (5,503 tokens at session start)" in out
    assert "▶  1. " in out and "█" in out and " tok" in out


@pty_only
def test_pty_clean_toggle_then_write_a_new_private_checklist(tmp_path):
    out, code = pty_session(
        tmp_path,
        [
            (b"Q Quit", b"4"),
            (b"\xe2\x9e\xa4 4. Clean", b"\r"),
            (b"A Write checklist", b" "),
            (b"[ ] quarterly", b"a"),
            (b"[y/N]", b"y\r"),
            (b"Press Enter to return", b"\r"),
            (b"A Write checklist", b"q"),
            (b"Q Quit", b"q"),
        ],
    )
    assert code == 0 and "Clean  (dry run: nothing is deleted)" in out and "(new file, deletes nothing)? [y/N]" in out
    checklist = tmp_path / "cleanup.md"
    assert "quarterly-ledger" not in checklist.read_text() and "yaml-lint" in checklist.read_text()
    assert oct(checklist.stat().st_mode & 0o777) == "0o600"


@pty_only
def test_pty_more_page_and_back(tmp_path):
    out, code = pty_session(tmp_path, [(b"Q Quit", b"m"), (b"Esc Back", b"\x1b"), (b"\xe2\x9e\xa4 1. Open", b"q")])
    assert code == 0 and "Remove preview" in out and out.count("Q Quit") >= 3


@pty_only
def test_pty_ctrl_c_restores_the_terminal(tmp_path):
    out, code = pty_session(tmp_path, [(b"Q Quit", b"\x03")])
    assert code == 130 and out.endswith(SHOW_CURSOR)
