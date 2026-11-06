"""Exits non-zero at once, printing a traceback-like message that names a raw path."""

import sys

sys.stderr.write("Traceback: boom at /Users/someone/private/path secret=hunter2hunter2\n")
sys.exit(3)
