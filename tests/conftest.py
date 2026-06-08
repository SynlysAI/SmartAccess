"""Shared test configuration.

Force Qt into headless (offscreen) mode before any PyQt import so desktop smoke
tests can run without a display.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
