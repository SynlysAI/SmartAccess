"""系统托盘控制器。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class TrayController(QObject):
    """管理系统托盘图标、右键菜单和气泡通知。

    主窗口关闭时最小化到托盘，云端远程任务与数据采集监听
    可以在后台继续运行。
    """

    restore_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon: QIcon, parent: QObject | None = None) -> None:
        """初始化托盘控制器。

        Args:
            icon: 托盘图标。
            parent: 父级对象。
        """

        super().__init__(parent)
        self._available = QSystemTrayIcon.isSystemTrayAvailable()
        self._tray = QSystemTrayIcon(icon, self)
        self._menu = QMenu()
        show_action = self._menu.addAction("显示主界面")
        show_action.triggered.connect(self.restore_requested.emit)
        self._menu.addSeparator()
        quit_action = self._menu.addAction("退出")
        quit_action.triggered.connect(self.quit_requested.emit)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.messageClicked.connect(self.restore_requested.emit)
        if self._available:
            self._tray.show()

    @property
    def available(self) -> bool:
        """返回系统托盘是否可用。"""

        return self._available

    def show_message(
        self,
        title: str,
        message: str,
        kind: QSystemTrayIcon.MessageIcon = (
            QSystemTrayIcon.MessageIcon.Information
        ),
    ) -> None:
        """显示托盘气泡通知。

        Args:
            title: 通知标题。
            message: 通知正文。
            kind: 通知图标类型。
        """

        if self._available:
            self._tray.showMessage(title, message, kind, 5000)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """单击或双击托盘图标时请求还原主窗口。

        Args:
            reason: 托盘图标激活原因。
        """

        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.restore_requested.emit()
