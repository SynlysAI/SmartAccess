"""Qt 应用启动。"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from smartaccess.desktop.shell.main_window import MainWindow
from smartaccess.desktop.shell.theme import apply_theme
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.logging import get_logger


def _load_app_icon() -> QIcon | None:
    """加载桌面应用图标。

    Returns:
        图标对象；图标文件不存在或无效时返回 None。
    """

    icon_path = Path(__file__).resolve().parents[4] / "resource" / "icon.png"
    if not icon_path.exists():
        return None
    icon = QIcon(str(icon_path))
    return icon if not icon.isNull() else None


def _set_windows_app_id() -> None:
    """设置 Windows 任务栏应用 ID。"""

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "SmartAccess.Desktop"
        )
    except Exception:  # noqa: BLE001 - 图标归组失败不应阻断启动
        return


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
    _set_windows_app_id()
    app.setApplicationDisplayName("SmartAccess")
    icon = _load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    apply_theme(app)
    window = MainWindow(settings, facade=facade)
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    logger.info("桌面主窗口已显示")
    return app.exec()
