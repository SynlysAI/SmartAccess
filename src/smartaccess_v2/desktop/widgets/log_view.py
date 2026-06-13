"""运行日志控件。"""

from __future__ import annotations

from PyQt6.QtWidgets import QTextEdit

from smartaccess_v2.desktop.viewmodels.monitoring_vm import MonitorLogEntry


class LogView(QTextEdit):
    """展示运行事件日志。"""

    def __init__(self, parent=None) -> None:
        """初始化日志视图。"""

        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

    def set_entries(self, entries: list[MonitorLogEntry]) -> None:
        """刷新日志内容。

        Args:
            entries: 日志行列表。
        """

        lines = [
            f"{entry.timestamp} [{entry.level}] {entry.message}"
            for entry in entries[-300:]
        ]
        self.setPlainText("\n".join(lines))
        self.moveCursor(self.textCursor().MoveOperation.End)
