"""Floods stdout with junk (a long unterminated line, then many lines) and never speaks the protocol."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import _pid  # noqa: E402,F401

try:
    sys.stdout.write("z" * 8_000_000)
    for _ in range(200):
        sys.stdout.write("junk\n" * 10_000)
    sys.stdout.flush()
except BrokenPipeError:
    sys.exit(0)
time.sleep(3600)
