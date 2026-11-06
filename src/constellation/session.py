"""The menu's thin I/O layer: pages, the commands they start, and the pause before coming back (logic lives in menu, analyze, cleanup)."""

import contextlib
import dataclasses
import importlib.metadata
import io
import json
import os
import select
import shutil
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from functools import partial
from pathlib import Path
from typing import Any

from . import analyze, banner, cleanup, frontdoor, next_step, scanfile
from . import pins as pin_file
from .cli_reports import ReportError, Scan, Style, style_for_stdout
from .cli_reports import load as load_scan
from .keys import RESIZE, Action, Cancel, edit, key_stream, parse_key, split_keys
from .menu import CLEAR, DAY, DIM, HIDE, OLIVE, SHOW, _c, choose, numbered, raw_mode, render, scan_age, step
from .menu import MORE as MORE_ENTRIES

PORT = 8765
CANCELLED = 130  # what a command that Esc or Ctrl-C stopped returns
Watch = Callable[[tuple[str, ...]], AbstractContextManager[None]]


class Exit(Exception):
    """Ends the menu with this exit code."""

    def __init__(self, code: int):
        self.code = code


class Session:
    """One run of the menu: pages, the commands they start, and the pause before coming back."""

    def __init__(
        self,
        run: Callable[[list[str]], int],
        scan_file: Path,
        config_dir: str,
        st: Style,
        confirm: Callable[[str], str],
        raw: Callable[[], AbstractContextManager[None]] | None,
        keys: Iterable[str] | None,
        now: Callable[[], float],
        version: str,
        load: Callable[[Path], Scan] = load_scan,
        pins: Path = pin_file.DEFAULT_CACHE,
        watch: Watch | None = None,
    ):
        self.load, self.pins, self.watch = load, pins, watch
        self.run, self.scan_file, self.cfg, self.st, self.confirm, self.raw, self.now, self.version = (
            run, scan_file, config_dir, st, confirm, raw, now, version,
        )  # fmt: skip
        self.keys = None if keys is None else iter(keys)

    def write(self, text: str) -> None:
        sys.stdout.write(banner.ascii_safe(text, sys.stdout.encoding))
        sys.stdout.flush()

    def page(
        self,
        lines_for: Callable[[int], list[str]],
        stepper: Callable[[int, str], int | Action],
        count: int,
        words: dict[str, str],
        index: int = 0,
    ) -> Action:
        """Show one interactive page and return the Action that ended it."""
        if self.keys is None:
            if not words:  # a page with no typed-number fallback: print it once and go back
                self.write("\n".join(lines_for(index)) + "\n")
                return Action("back")
            return numbered(self.confirm, self.write, lines_for, count, words)
        self.write(CLEAR + HIDE)
        with (self.raw or contextlib.nullcontext)():
            action = choose(self.sized(self.keys), self.write, lines_for, stepper, index)
        self.write(SHOW + CLEAR)
        return action

    def sized(self, keys: Iterator[str]) -> Iterator[str]:
        """The keys, with the page width following the window: a resize re-reads the width before the page redraws."""
        for key in keys:
            if key == "resize":
                self.st = dataclasses.replace(self.st, width=style_for_stdout().width)
            yield key

    def framed(self, view: analyze.View | cleanup.View) -> Callable[[int], list[str]]:
        return lambda i: view.lines(i, st=self.st)  # reads the width at draw time, so a resize reaches it

    def height(self) -> int | None:
        return shutil.get_terminal_size().lines if self.keys is not None and sys.stdout.isatty() else None

    def say(self, text: str, code: int = 0) -> int:
        self.write(text)
        return code

    def call(self, argv: list[str], stop: tuple[str, ...] = ("esc",)) -> int:
        """Run a subcommand; Ctrl-C (or a key in `stop`, where the terminal can watch for one) cancels just this command."""
        try:
            with self.watch(stop) if self.watch else contextlib.nullcontext(), contextlib.suppress(SystemExit):
                # argparse exits after --help and --version
                return self.run(argv)
        except KeyboardInterrupt:
            return CANCELLED
        return 0

    def stopped(self, code: int) -> str:
        return _c(self.st, "31", "\n  Cancelled" if code == CANCELLED else f"\n  Stopped: exit code {code}") + "\n"

    def quiet(self, argv: list[str], live: bool = False) -> tuple[int, str]:
        """Run a subcommand with its output captured (`live`: stderr stays on the terminal, for the scan's progress bar)."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.nullcontext() if live else contextlib.redirect_stderr(buf):
            code = self.call(argv)
        return code, buf.getvalue()

    def pause(self) -> None:
        try:
            back = self.confirm("\n  Press Enter or Esc to return (q to quit) ")
        except Cancel:
            return
        except EOFError:
            raise Exit(0) from None
        if back.strip().lower() == "q":
            raise Exit(0)

    def show(self, title: str, work: Callable[[], int], hint: str = "Esc to cancel", wait: bool = True) -> None:
        """A command's screen: its title, its output, a note if it stopped, then wait for Enter (`wait` False: only after a failure)."""
        note = _c(self.st, DIM, f"  {hint}") + "\n" if self.watch and hint else ""
        self.write((CLEAR if self.keys is not None else "") + _c(self.st, "1;" + OLIVE, f"  ▸ {title}") + "\n" + note + "\n")
        code = work()
        if code:
            self.write(self.stopped(code))
        if code or wait:
            self.pause()

    def commands(self, title: str, steps: list[list[str]], scan: bool = True) -> None:
        if scan and not self.ensure_scan():
            return
        self.show(title, lambda: next((code for code in map(self.call, steps) if code), 0))

    def fresh(self) -> bool:
        age = scan_age(self.scan_file, self.now())
        return age is not None and age < DAY

    def yes(self, ask: str, plain: bool = False) -> bool:
        """A y/N question: only "y" says yes; Esc, Enter or anything else says no and does nothing."""
        tag = ("(y/N, Esc to cancel) " if self.watch else "(y/N) ") if plain else "[y/N, Esc to cancel] " if self.watch else "[y/N] "
        try:
            return self.confirm(ask + tag).strip().lower() == "y"
        except Cancel:
            return False

    def confirm_scan(self) -> bool:
        if not self.scan_file.is_file():
            return self.yes("Scan first? ", plain=True)
        return self.yes(f"No fresh scan. Run `constellation scan {self.cfg} --offline` (reads {self.cfg} locally, sends nothing)? ")

    def ensure_scan(self) -> bool:
        """True when a scan from the last day exists, or the user agreed to make one and it worked."""
        if self.fresh():
            return True
        if not self.confirm_scan():
            return False
        return self.run_scan()

    def run_scan(self, hint: bool = False) -> bool:
        """Scan offline with a progress line, then say what was found; True when it worked."""
        self.write("  Scanning your setup (offline, nothing is sent)...\n")
        code, text = self.quiet(["scan", self.cfg, "--offline"], live=True)
        if code:
            self.write(text + self.stopped(code))
            self.pause()
            return False
        try:
            data = json.loads(self.scan_file.read_text())
        except (OSError, ValueError):
            data = None
        self.write("  " + frontdoor.done_line(data) + "\n")
        if hint and (line := next_step.hint_line(self.st, "scan", None)):
            self.write("  " + line + "\n")
        return True

    def scan_entry(self) -> None:
        """Entry 1: say what the scan reads and writes, ask, then scan."""
        self.write(("" if self.keys is None else CLEAR) + _c(self.st, "1;" + OLIVE, "  ▸ Scan") + "\n\n")
        self.write("\n".join(frontdoor.scan_intro(self.cfg, str(self.scan_file))) + "\n\n")
        if not self.yes("  Scan now? "):
            return
        if self.run_scan(hint=True):
            self.pause()

    def prompt(self, question: str) -> str:
        self.write(("" if self.keys is None else CLEAR) + f"\n  {question} " + (_c(self.st, DIM, "(Esc to cancel) ") if self.watch else ""))
        try:
            return frontdoor.clean_answer(self.confirm(""))
        except (EOFError, Cancel):
            return ""

    def open_graph(self) -> None:
        demo = not self.scan_file.is_file() and not self.ensure_scan()

        def serve() -> int:
            if demo:
                self.write("  No scan of your setup, so this shows the packaged demo (invented data).\n")
            argv = ["open", "demo" if demo else str(self.scan_file), "--port", str(PORT)]
            code = self.call(argv + ["--menu"] if self.watch else argv, ("esc", "q"))
            return 0 if code == CANCELLED else code  # Ctrl-C is how the server stops

        self.show("Open", serve, hint="", wait=False)

    def collect(self, rescan: bool) -> tuple[list[analyze.Row], int | None] | None:
        if rescan:
            self.write(CLEAR + "\r\n".join(analyze.render([], 0, self.st, None, "Scanning…")) + "\r\n")
            code, text = self.quiet(["scan", self.cfg, "--offline"], live=True)
            if code:
                self.write(text + self.stopped(code))
                self.pause()
                return None
        code, text = self.quiet(["cost", "--json"])
        if code:
            self.write(text + self.stopped(code))
            self.pause()
            return None
        try:
            scan = json.loads(self.scan_file.read_text())
        except (OSError, ValueError):
            scan = {}
        cost = json.loads(text)
        return analyze.rows_from(cost, scan), cost["total"]

    def analyze(self) -> None:
        state = self.collect(False) if self.fresh() else self.confirm_scan() and self.collect(True) or None
        index = 0
        while state is not None:
            view = analyze.View(*state)
            action = self.page(self.framed(view), view.key, len(view.rows), {}, index)
            index = action.choice
            if action.kind in ("back", "quit"):
                return
            if action.kind == "refresh":
                state = self.collect(True)
                index = 0
            elif action.kind == "open":
                self.open_graph()
            elif view.rows:
                row = view.rows[index]
                if action.kind == "why":
                    self.commands(row.name, [["why", row.name]], scan=False)
                elif action.kind == "preview":
                    self.commands(row.name, [["remove-preview", row.name]], scan=False)
                elif action.kind == "file":
                    self.show(row.name, partial(self.say, f"  {row.path or 'no file path recorded for this Item'}\n"))

    def clean(self) -> None:
        """The Clean dry run: a grouped list of what the verdicts would let go. Only the checklist file is ever written, and only new."""
        if not self.ensure_scan():
            return
        try:
            view = cleanup.View(self.load(self.scan_file))
        except ReportError as error:
            self.show("Clean", partial(self.say, f"  {error}\n", 1))
            return
        index = 0
        while True:
            action = self.page(self.framed(view), view.key, len(view.props), {}, index)
            index = action.choice
            if action.kind in ("back", "quit"):
                return
            if not view.props:
                continue
            item = view.props[index]
            if action.kind == "why":
                self.commands(item.name, [["why", item.name], ["remove-preview", item.name]], scan=False)
            elif action.kind == "pin" and index < view.n:
                try:
                    pin_file.add(self.pins, item.id)
                    view = cleanup.View(self.load(self.scan_file), view.checked)
                except (OSError, ValueError, ReportError) as error:
                    self.show(item.name, partial(self.say, f"  Could not pin: {error}\n", 1))
                index = min(index, max(0, len(view.props) - 1))
            elif action.kind == "write":
                self.write_checklist(view.chosen())

    def write_checklist(self, chosen: list[cleanup.Prop]) -> None:
        path = self.scan_file.parent / "cleanup.md"
        self.write(("" if self.keys is None else CLEAR) + "\n")
        if not self.yes(f"  Write a checklist of {len(chosen)} Items to {path.resolve()} (new file, deletes nothing)? "):
            return

        def work() -> int:
            try:
                cleanup.write_new(path, cleanup.checklist(chosen))
            except FileExistsError:
                return self.say(f"  {path} already exists, so nothing was written. Move it aside and try again.\n", 1)
            except OSError as error:
                return self.say(f"  Could not write {path}: {error}\n", 1)
            hint = next_step.hint_line(self.st, "clean", None)
            return self.say(
                f"  Wrote {path.resolve()}\n  Constellation never edits your config; make each change by hand.\n"
                + (f"  {hint}\n" if hint else "")
            )

        self.show("Clean", work)

    def more(self) -> None:
        index = 0
        entries = MORE_ENTRIES
        while True:
            action = self.page(
                lambda i: render(i, self.st, self.version, entries, False, height=self.height()),
                lambda i, k: step(i, k, len(entries), False),
                len(entries),
                {"b": "back", "q": "quit"},
                index,
            )
            index = action.choice if action.kind == "run" else index
            if action.kind == "back":
                return
            if action.kind == "quit":
                raise Exit(0)
            if action.kind == "interrupt":
                raise Exit(130)
            cmd = frontdoor.MORE[action.choice]
            answer = ""
            if cmd.ask:
                answer = self.prompt(cmd.ask)
                if not answer:
                    continue
            self.commands(cmd.name, [frontdoor.argv_for(cmd, self.cfg, answer)], scan=cmd.scan)

    def entry(self, choice: int) -> None:
        if choice == 0:
            self.scan_entry()
        elif choice == 1:
            self.open_graph()
        elif choice == 2:
            self.analyze()
        elif choice == 3:
            query = self.prompt("What does the skill do?")
            if query:
                cards = (
                    ["--limit", str((height - 6) // 5)] if (height := self.height()) and height < 46 else []
                )  # a card is 5 lines; keep the top in view
                self.commands("Find", [["find", query, "--config-dir", self.cfg, *cards]], scan=False)
        elif choice == 4:
            self.clean()
        else:
            self.commands("Status", [["doctor"], ["weekly"]])

    def main_frame(self, index: int) -> list[str]:
        """The main menu; with no saved scan it says so and Scan explains itself."""
        first_run = not self.scan_file.is_file()
        return render(
            index,
            self.st,
            self.version,
            frontdoor.main_entries(first_run),
            note=frontdoor.NO_SCAN if first_run else "",
            height=self.height(),
        )

    def loop(self) -> int:
        words = {"q": "quit", "m": "more", "v": "version", "u": "update"}
        index = 0
        try:
            while True:
                action = self.page(self.main_frame, step, 6, words, index)
                index = action.choice if action.kind == "run" else index
                if action.kind == "quit":
                    return 0
                if action.kind == "interrupt":
                    return 130
                if action.kind == "more":
                    self.more()
                elif action.kind in ("version", "update"):
                    self.show(action.kind.title(), partial(self.call, ["--version" if action.kind == "version" else "update"]))
                else:
                    self.entry(action.choice)
        except Exit as stop:
            return stop.code
        finally:
            if self.keys is not None:
                self.write(SHOW)


def launch(
    run: Callable[[list[str]], int],
    scan_file: Path | None = None,
    config_dir: str | None = None,
    *,
    st: Style,
    confirm: Callable[[str], str] = input,
    raw: Callable[[], AbstractContextManager[None]] | None = None,
    keys: Iterable[str] | None = None,
    now: Callable[[], float] = time.time,
    load: Callable[[Path], Scan] = load_scan,
    pins: Path | None = None,
    watch: Watch | None = None,
) -> int:
    """Show the menu and run the chosen entries through `run` (cli.main) until the user quits. Returns the exit code."""
    version = importlib.metadata.version("constellation-cli")
    return Session(
        run,
        scan_file or scanfile.target(),
        config_dir or str(Path.home() / ".claude"),
        st,
        confirm,
        raw,
        keys,
        now,
        version,
        load,
        pins or pin_file.DEFAULT_CACHE,
        watch,
    ).loop()


def line_reader(
    typed: Iterator[str], raw: Callable[[], AbstractContextManager[None]], write: Callable[[str], object]
) -> Callable[[str], str]:
    """A prompt that reads keys itself, so Esc can cancel it (raises Cancel); Enter returns the text."""

    def read(prompt: str) -> str:
        write(prompt)
        text = ""
        with raw():
            for key in typed:
                new, status = edit(text, key)
                if status:
                    write("\r\n")
                    if status == "cancel":
                        raise Cancel
                    return text
                write(key if len(new) > len(text) else "\b \b" if len(new) < len(text) else "")
                text = new
        raise EOFError

    return read


@contextlib.contextmanager
def watch_keys(
    fd: int, termios: Any, tty: Any, stop: tuple[str, ...], interrupt: Callable[[], object] = lambda: os.kill(os.getpid(), signal.SIGINT)
) -> Iterator[None]:
    """While a command runs: Ctrl-C still works, and any key in `stop` (Esc) interrupts the main thread as Ctrl-C would."""
    saved = termios.tcgetattr(fd)
    done = threading.Event()

    def listen() -> None:
        while not done.is_set():
            if select.select([fd], [], [], 0.1)[0]:
                data = os.read(fd, 64)
                if not data or any(parse_key(k) in stop for k in split_keys(data)):
                    interrupt()
                    return

    tty.setcbreak(fd)
    watcher = threading.Thread(target=listen, daemon=True)
    watcher.start()
    try:
        yield
    finally:
        done.set()
        watcher.join()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def terminal() -> tuple[Callable[[], AbstractContextManager[None]], Iterable[str], Callable[[str], str], Watch] | None:
    """Raw-mode context, the stream of keys, a text prompt and a key watcher for the real terminal, or None where termios is missing."""
    try:
        import termios
        import tty
    except ImportError:
        return None
    fd = sys.stdin.fileno()

    def raw() -> AbstractContextManager[None]:
        return raw_mode(fd, termios, tty)

    def read() -> bytes:
        """Bytes typed, or RESIZE when the window changed size while waiting."""
        size = shutil.get_terminal_size()
        while not select.select([fd], [], [], 0.2)[0]:
            if shutil.get_terminal_size() != size:
                return RESIZE
        return os.read(fd, 64)

    typed = key_stream(read, fold=False)

    def write(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    return raw, key_stream(read), line_reader(typed, raw, write), partial(watch_keys, fd, termios, tty)


def open_menu(run: Callable[[list[str]], int]) -> int:
    """Entry point used by cli.main when stdin and stdout are both a TTY. Ctrl-C exits 130 with the terminal restored."""
    with contextlib.suppress(AttributeError, ValueError):  # a replaced stdout may not reconfigure
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]  # command output with a symbol this terminal lacks must not crash the menu
    raw, keys, confirm, watch = terminal() or (None, None, input, None)
    try:
        return launch(run, st=style_for_stdout(), raw=raw, keys=keys, confirm=confirm, watch=watch)
    except KeyboardInterrupt:
        return 130
