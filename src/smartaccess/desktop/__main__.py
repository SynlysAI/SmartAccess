"""``python -m smartaccess.desktop`` launches the SmartAccess workbench."""

from __future__ import annotations

import sys

from smartaccess.bootstrap import run_desktop

if __name__ == "__main__":
    sys.exit(run_desktop())
