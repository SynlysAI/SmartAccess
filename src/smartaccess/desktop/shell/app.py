"""Application entry: build the QApplication, apply theme, show the main window."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from smartaccess.desktop.shell.main_window import MainWindow
from smartaccess.desktop.shell.theme import apply_theme


def run_app(facade) -> int:
    """Launch the desktop workbench against a runtime facade. Blocks until exit."""

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow(facade)
    window.show()
    return app.exec()
