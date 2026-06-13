"""Qt 应用启动。"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from smartaccess_v2.desktop.shell.main_window import MainWindow
from smartaccess_v2.desktop.shell.theme import apply_theme
from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.shared.config.settings import AppSettings
from smartaccess_v2.shared.logging import get_logger


def run_app(settings: AppSettings, facade: RuntimeFacade | None = None) -> int:
    """启动 Qt 桌面应用。

    Args:
        settings: 应用配置。
        facade: 可选运行时门面。

    Returns:
        Qt 应用退出码。
    """

    logger = get_logger()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationDisplayName("SmartAccess")
    apply_theme(app)
    window = MainWindow(settings, facade=facade)
    window.show()
    logger.info("桌面主窗口已显示")
    return app.exec()
