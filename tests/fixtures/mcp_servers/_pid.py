"""Fixture helper: record this process id so tests can prove it was reaped. Invented servers only."""

import os

path = os.environ.get("FIXTURE_PIDFILE")
if path:
    with open(path, "w") as handle:
        handle.write(str(os.getpid()))
