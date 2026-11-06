"""A tiny VT100 screen emulator and pty driver for tests: run a program in a real pseudo-terminal, send keys, read the screen."""

import codecs
import fcntl
import os
import pty
import re
import select
import signal
import struct
import termios
import time

_CSI = re.compile(r"\x1b\[([?0-9;]*)([A-Za-z])")


class Screen:
    """Cells, cursor, deferred autowrap, scrolling and the sequences Constellation writes (cursor moves, erase, SGR, show/hide cursor)."""

    def __init__(self, rows: int, cols: int):
        self.rows, self.cols = rows, cols
        self.grid = [[" "] * cols for _ in range(rows)]
        self.r = self.c = 0
        self.wrap = False
        self.cursor_visible = True
        self.scrolled = 0  # lines pushed off the top: a frame taller than the screen shows up here
        self.pending = ""
        self.sgr = ""  # last SGR seen, to tell colour from plain

    def _scroll(self) -> None:
        self.grid.pop(0)
        self.grid.append([" "] * self.cols)
        self.scrolled += 1

    def _down(self) -> None:
        if self.r == self.rows - 1:
            self._scroll()
        else:
            self.r += 1

    def feed(self, text: str) -> None:
        text = self.pending + text
        tail = re.search(r"\x1b(\[[?0-9;]*)?$", text)  # an escape cut in half by a read waits for the rest
        self.pending, text = (text[tail.start() :], text[: tail.start()]) if tail else ("", text)
        pos = 0
        while pos < len(text):
            m = _CSI.match(text, pos)
            if m:
                self._csi(m.group(1), m.group(2))
                pos = m.end()
                continue
            ch = text[pos]
            pos += 1
            if ch == "\x1b":
                continue
            if ch == "\r":
                self.c, self.wrap = 0, False
            elif ch == "\n":
                self._down()
                self.wrap = False
            elif ch == "\b":
                self.c, self.wrap = max(0, self.c - 1), False
            elif ch >= " ":
                if self.wrap:
                    self.c, self.wrap = 0, False
                    self._down()
                self.grid[self.r][self.c] = ch
                if self.c == self.cols - 1:
                    self.wrap = True
                else:
                    self.c += 1

    def _csi(self, args: str, final: str) -> None:
        nums = [int(n) if n else 0 for n in args.lstrip("?").split(";")] if args.lstrip("?") else []
        n = nums[0] if nums and nums[0] else 1
        if final == "m":
            self.sgr = args
        elif final in "hl" and args == "?25":
            self.cursor_visible = final == "h"
        elif final == "A":
            self.r, self.wrap = max(0, self.r - n), False
        elif final == "B":
            self.r, self.wrap = min(self.rows - 1, self.r + n), False
        elif final == "C":
            self.c, self.wrap = min(self.cols - 1, self.c + n), False
        elif final == "D":
            self.c, self.wrap = max(0, self.c - n), False
        elif final == "F":
            self.r, self.c, self.wrap = max(0, self.r - n), 0, False
        elif final == "E":
            self.r, self.c, self.wrap = min(self.rows - 1, self.r + n), 0, False
        elif final == "H":
            self.r, self.c, self.wrap = min(self.rows, max(1, n)) - 1, 0, False
            if len(nums) > 1:
                self.c = min(self.cols, max(1, nums[1])) - 1
        elif final == "J":
            mode = nums[0] if nums else 0
            if mode == 2:
                self.grid = [[" "] * self.cols for _ in range(self.rows)]
            elif mode == 0:
                self.grid[self.r][self.c :] = [" "] * (self.cols - self.c)
                for row in range(self.r + 1, self.rows):
                    self.grid[row] = [" "] * self.cols
        elif final == "K":
            mode = nums[0] if nums else 0
            if mode == 0:
                self.grid[self.r][self.c :] = [" "] * (self.cols - self.c)
            elif mode == 2:
                self.grid[self.r] = [" "] * self.cols

    def lines(self) -> list[str]:
        out = ["".join(row).rstrip() for row in self.grid]
        while out and not out[-1]:
            out.pop()
        return out

    def text(self) -> str:
        return "\n".join(self.lines())


class Term:
    """argv in a pty of rows x cols; `send` types, `settle` reads until quiet, `screen` is what a user would see."""

    def __init__(self, argv: list[str], rows: int, cols: int, env: dict[str, str]):
        self.rows, self.cols = rows, cols
        self.screen = Screen(rows, cols)
        self.raw = b""
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe(argv[0], argv, env)
        self.pid, self.fd = pid, fd
        self.resize(rows, cols)
        self.status: int | None = None

    def resize(self, rows: int, cols: int) -> None:
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        os.kill(self.pid, signal.SIGWINCH)

    def settle(self, quiet: float = 0.4, limit: float = 20.0) -> None:
        end, last = time.time() + limit, time.time()
        while time.time() < end and time.time() - last < quiet:
            if select.select([self.fd], [], [], 0.05)[0]:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                self.raw += data
                self.screen.feed(self.decoder.decode(data))
                last = time.time()

    def send(self, data: bytes | str, quiet: float = 0.4, limit: float = 20.0) -> str:
        os.write(self.fd, data.encode() if isinstance(data, str) else data)
        self.settle(quiet, limit)
        return self.screen.text()

    def exit_code(self, wait: float = 5.0) -> int | None:
        end = time.time() + wait
        while time.time() < end:
            self.settle(0.1, 0.3)
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.status = os.waitstatus_to_exitcode(status)
                return self.status
        return None

    def close(self) -> None:
        if self.status is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except OSError:
                pass
        os.close(self.fd)
