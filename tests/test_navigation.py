"""Getting around the menu: a way back from every screen and prompt, Ctrl-C and Esc that cancel one command, and Open."""

import socket
import subprocess
import threading
import webbrowser

import pytest
from test_menu import CANCEL, ESC, FakeTermios, Runner, Session, go, pty_only, pty_session

from constellation import opener, session
from constellation.keys import Cancel

# ---- Esc at a prompt does nothing ----


def test_esc_at_the_scan_question_runs_nothing(tmp_path):
    s = go(tmp_path, "6", "enter", "q", say=(CANCEL,))
    assert s.runner.calls == [] and len(s.asked) == 1 and s.code == 0


def test_esc_at_the_find_question_and_the_item_question_runs_nothing(tmp_path):
    assert go(tmp_path, "4", "enter", "q", typed=(CANCEL,)).runner.calls == []
    assert go(tmp_path / "m", "m", "6", "enter", "esc", "q", age=0, typed=(CANCEL,)).runner.calls == []


def test_esc_at_the_checklist_question_writes_nothing(tmp_path):
    s = go(tmp_path, "5", "enter", "a", "esc", "q", age=0, say=(CANCEL,))
    assert s.code == 0 and not (tmp_path / "cleanup.md").exists() and s.asked[0].startswith("  Write a checklist")


def test_esc_at_the_pause_goes_back_instead_of_quitting(tmp_path, capsys):
    s = go(tmp_path, "6", "enter", "q", age=0, pause=(CANCEL,), capsys=capsys)
    assert s.code == 0 and s.runner.calls == [["doctor"], ["weekly"]] and s.out.count("➤ 6. Status") == 2


# ---- a cancelled command ----


def test_a_cancelled_scan_says_so_and_the_menu_stays_up(tmp_path, capsys):
    s = go(tmp_path, "6", "enter", "q", runner=Runner(boom={"scan": KeyboardInterrupt()}), capsys=capsys)
    assert s.code == 0 and s.runner.calls == [["scan", "/cfg", "--offline"]]
    assert "\n  Cancelled\n" in s.out and "Stopped" not in s.out and s.out.count("➤ 6. Status") == 2


def test_cancelling_the_analyze_scan_returns_to_the_menu(tmp_path, capsys):
    s = go(tmp_path, "3", "enter", "q", runner=Runner(boom={"scan": KeyboardInterrupt()}), capsys=capsys)
    assert s.code == 0 and "\n  Cancelled\n" in s.out and s.runner.calls == [["scan", "/cfg", "--offline"]]
    s = go(tmp_path / "c", "3", "enter", "q", age=0, runner=Runner(boom={"cost": KeyboardInterrupt()}), capsys=capsys)
    assert s.code == 0 and "\n  Cancelled\n" in s.out


def test_a_cancelled_command_is_red_with_colour(tmp_path, capsys):
    s = Session(tmp_path, "6", "enter", "q", age=0, runner=Runner(boom={"doctor": KeyboardInterrupt()}))
    s.run(session.Style(True, 80))
    assert f"{ESC}[31m\n  Cancelled{ESC}[0m" in capsys.readouterr().out


def test_the_terminal_watcher_is_told_which_keys_stop_what(tmp_path, capsys):
    s = go(tmp_path, "6", "enter", "q", age=0, watching=True, capsys=capsys)
    assert s.watched == [("esc",), ("esc",)] and "  ▸ Status\n  Esc to cancel\n\n" in s.out
    s = go(tmp_path / "o", "2", "enter", "q", age=0, watching=True, capsys=capsys)
    assert s.runner.calls == [["open", str(s.scan), "--port", "8765", "--menu"]] and s.watched == [("esc", "q")]
    assert "Esc to cancel" not in s.out and s.asked == []


def test_prompts_say_how_to_cancel_only_where_esc_works(tmp_path, capsys):
    s = go(tmp_path, "4", "enter", "q", typed=("x",), watching=True, capsys=capsys)
    assert "\n  What does the skill do? (Esc to cancel) " in s.out
    s = go(tmp_path / "y", "6", "enter", "q", say=("n",), watching=True)
    assert s.asked[0] == "Scan first? (y/N, Esc to cancel) "


def test_a_failed_open_waits_for_enter(tmp_path, capsys):
    s = go(tmp_path, "2", "enter", "q", age=0, runner=Runner({"open": 2}), capsys=capsys)
    assert "Stopped: exit code 2" in s.out and len(s.asked) == 1


# ---- the key-reading prompt and the Esc watcher ----


def reader(keys):
    out, entered = [], []

    class Raw:
        def __enter__(self):
            entered.append("in")

        def __exit__(self, *exc):
            entered.append("out")

    return session.line_reader(iter(keys), Raw, out.append), out, entered


def test_line_reader_types_edits_and_returns_on_enter():
    read, out, entered = reader(["H", "i", "x", "backspace", "left", "enter"])
    assert read("? ") == "Hi" and entered == ["in", "out"]
    assert out == ["? ", "H", "i", "x", "\b \b", "", "\r\n"]


def test_line_reader_esc_cancels_and_end_of_input_fails():
    read, out, entered = reader(["a", "esc"])
    with pytest.raises(Cancel):
        read("? ")
    assert out[-1] == "\r\n" and entered == ["in", "out"]
    with pytest.raises(EOFError):
        reader(["a"])[0]("? ")


class Tty(FakeTermios):
    def setcbreak(self, fd):
        self.calls.append(("cbreak", fd))


def run_watch(data, stop=("esc",)):
    import os

    read, write = os.pipe()
    t, hit = Tty(), threading.Event()
    try:
        with session.watch_keys(read, t, t, stop, hit.set):
            os.write(write, data)
            fired = hit.wait(1.0)
    finally:
        os.close(read)
        os.close(write)
    return fired, t.calls, read


def test_watch_keys_interrupts_on_a_stop_key_and_restores_the_terminal():
    fired, calls, fd = run_watch(b"\x1b")
    assert fired and calls == [("get", fd), ("cbreak", fd), ("set", fd, 1, "saved")]
    assert run_watch(b"q", ("esc", "q"))[0] and run_watch(b"x\x1b[B")[0] is False


# ---- the opener ----


class Clock:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_wait_ready_polls_until_the_server_accepts():
    clock, tries = Clock(), iter([False, False, True])
    assert opener.wait_ready(lambda: next(tries), lambda: True, clock=clock, sleep=clock.sleep) is True
    assert clock.slept == [0.1, 0.1]


def test_wait_ready_gives_up_after_the_timeout_or_when_the_server_died():
    clock = Clock()
    assert opener.wait_ready(lambda: False, lambda: True, timeout=1.0, every=0.4, clock=clock, sleep=clock.sleep) is False
    assert clock.slept == [0.4, 0.4, 0.4]  # tries at 0, 0.4, 0.8, 1.2; gives up at 1.2
    assert opener.wait_ready(lambda: True, lambda: False) is False
    assert opener.wait_ready(lambda: True, lambda: True, timeout=0) is True


class Run:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, 0)


def test_open_url_uses_the_platforms_own_opener():
    for platform, command in [("darwin", "open"), ("linux", "xdg-open")]:
        run = Run()
        assert opener.open_url("http://h/", platform, run, fallback=lambda u: pytest.fail("no fallback")) is True
        assert run.calls[0][0] == [command, "http://h/"] and run.calls[0][1]["check"] is True and run.calls[0][1]["timeout"] == 10
    opened = []
    assert opener.open_url("http://h/", "win32", Run(), opened.append, lambda u: pytest.fail("no fallback")) is True
    assert opened == ["http://h/"]


def test_open_url_falls_back_to_webbrowser_when_the_opener_fails():
    seen = []
    for error in (FileNotFoundError("xdg-open"), subprocess.CalledProcessError(1, "open"), subprocess.TimeoutExpired("open", 10)):
        assert opener.open_url("http://h/", "linux", Run(error), fallback=lambda u: seen.append(u) or True) is True
    assert seen == ["http://h/"] * 3
    assert opener.open_url("http://h/", "freebsd", Run(), fallback=lambda u: seen.append(u) or True) is True and len(seen) == 4
    assert opener.open_url("http://h/", "freebsd", Run(), fallback=lambda u: False) is False
    assert opener.open_url("http://h/", "win32", Run(), lambda u: (_ for _ in ()).throw(OSError()), lambda u: False) is False


def test_open_url_says_no_when_there_is_no_browser():
    def none(url):
        raise webbrowser.Error("no browser")

    assert opener.open_url("http://h/", "linux", Run(OSError()), fallback=none) is False


def test_hyperlink_only_where_the_terminal_supports_it():
    link = "\033]8;;http://h/\033\\http://h/\033]8;;\033\\"
    for env in ({"TERM_PROGRAM": "iTerm.app"}, {"KITTY_WINDOW_ID": "1"}, {"VTE_VERSION": "5000"}, {"TERM_PROGRAM": "WezTerm"}):
        assert opener.hyperlink("http://h/", env, True) == link
    for env in ({}, {"TERM_PROGRAM": "Apple_Terminal"}, {"VTE_VERSION": "4999"}, {"VTE_VERSION": ""}, {"VTE_VERSION": "x"}):
        assert opener.hyperlink("http://h/", env, True) == "http://h/"
    assert opener.hyperlink("http://h/", {"TERM_PROGRAM": "iTerm.app"}, False) == "http://h/"


# ---- the real program in a pseudo-terminal ----

ESC_KEY, CTRL_C = b"\x1b", b"\x03"


@pty_only
def test_pty_esc_goes_back_from_every_screen_and_prompt(tmp_path):
    out, code = pty_session(
        tmp_path,
        [
            (b"Q Quit", b"4"),  # Find: Esc at the question
            (b"\xe2\x9e\xa4 4. Find", b"\r"),
            (b"(Esc to cancel)", ESC_KEY),
            (b"U Update | Q Quit", b"m"),  # More, Remove preview: Esc at the question, then Esc back
            (b"Esc Back", b"6"),
            (b"\xe2\x9e\xa4 6. Remove", b"\r"),
            (b"(Esc to cancel)", ESC_KEY),
            (b"Esc Back", ESC_KEY),
            (b"U Update | Q Quit", b"5"),  # Clean: Esc at the checklist question, then back with the left arrow
            (b"\xe2\x9e\xa4 5. Clean", b"\r"),
            (b"A Write checklist", b"a"),
            (b"Esc to cancel]", ESC_KEY),
            (b"A Write checklist", b"\x1b[D"),
            (b"U Update | Q Quit", b"3"),  # Analyze: back with b
            (b"\xe2\x9e\xa4 3. Analyze", b"\r"),
            (b"Esc/Q Back", b"b"),
            (b"U Update | Q Quit", b"6"),  # a command screen: Esc at the pause
            (b"\xe2\x9e\xa4 6. Status", b"\r"),
            (b"Press Enter or Esc to return", ESC_KEY),
            (b"\xe2\x9e\xa4 6. Status", b"q"),
        ],
    )
    assert code == 0 and not (tmp_path / "cleanup.md").exists() and "Esc to cancel" in out


@pty_only
def test_pty_ctrl_c_in_a_page_goes_back_and_ctrl_c_in_the_menu_quits(tmp_path):
    out, code = pty_session(tmp_path, [(b"Q Quit", b"m"), (b"Esc Back", CTRL_C), (b"\xe2\x9e\xa4 1. Scan", CTRL_C)])
    assert code == 130 and out.endswith("\x1b[?25h")


SLOW = "import sys, time; from constellation import cli; cli.main_orig = cli.main; sys.exit(cli.main())"


@pty_only
def test_pty_ctrl_c_and_esc_cancel_a_running_command(tmp_path):
    # `scan` is slow enough (embedding load) to interrupt only if forced, so stand in for it with a command that waits.
    program = (
        "import sys, time\n"
        "from constellation import cli, session\n"
        "def run(argv):\n"
        "    if argv[0] == 'doctor':\n"
        "        print('working'); sys.stdout.flush(); time.sleep(30)\n"
        "    return cli.main(argv)\n"
        "sys.exit(session.open_menu(run))\n"
    )
    for key in (CTRL_C, ESC_KEY):
        out, code = pty_session(
            tmp_path,
            [
                (b"Q Quit", b"6"),
                (b"\xe2\x9e\xa4 6. Status", b"\r"),
                (b"working", key),
                (b"Cancelled", b""),
                (b"Press Enter or Esc to return", b"\r"),
                (b"\xe2\x9e\xa4 6. Status", b"q"),
            ],
            program,
        )
        assert code == 0 and "Esc to cancel" in out and "Cancelled" in out


@pty_only
def test_pty_open_serves_opens_the_browser_and_esc_stops_the_server(tmp_path):
    with socket.socket() as probe:  # a free port, so another program on 8765 cannot get in the way
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("open", "xdg-open"):  # stand-ins, so no real browser starts
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "$1" > {tmp_path}/opened.txt\n')
        stub.chmod(0o755)
    program = (
        "import sys\nfrom pathlib import Path\nfrom constellation import server, cli, session\n"
        f"server.STATIC = Path({str(static)!r})\nsession.PORT = {port}\nsys.exit(cli.main())\n"
    )
    out, code = pty_session(
        tmp_path,
        [
            (b"Q Quit", b"2"),
            (b"\xe2\x9e\xa4 2. Open", b"\r"),
            (b"Press Esc or q to stop the server and go back", b""),
            (b"Serving at", b""),
            (f"\n  http://127.0.0.1:{port}/".encode(), ESC_KEY),
            (b"\xe2\x9e\xa4 2. Open", b"q"),
        ],
        program,
        f"{bin_dir}:",
    )
    assert code == 0 and (tmp_path / "opened.txt").read_text().strip() == f"http://127.0.0.1:{port}/"
    assert "Press Enter" not in out.split("Serving at")[1].split("2. Open")[0]
