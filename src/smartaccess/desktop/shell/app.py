"""Application entry: build the QApplication, apply theme, show the main window."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from smartaccess.desktop.shell.main_window import MainWindow
from smartaccess.desktop.shell.theme import apply_theme


def _load_app_icon() -> QIcon | None:
    icon_path = Path(__file__).resolve().parents[4] / "resource" / "icon.png"
    if not icon_path.exists():
        return None
    icon = QIcon(str(icon_path))
    return icon if not icon.isNull() else None


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SmartAccess.Desktop")
    except Exception:
        return


def run_app(facade, *, provider_modes: dict[str, str] | None = None) -> int:
    """Launch the desktop workbench against a runtime facade. Blocks until exit."""

    app = QApplication.instance() or QApplication(sys.argv)
    _set_windows_app_id()
    app.setApplicationDisplayName("SmartAccess")
    icon = _load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    apply_theme(app)
    window = MainWindow(facade, provider_modes=provider_modes)
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    return app.exec()
