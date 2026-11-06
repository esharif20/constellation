"""Starts, reads nothing, answers nothing."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import _pid  # noqa: E402,F401

time.sleep(3600)
