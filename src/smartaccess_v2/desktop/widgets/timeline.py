"""运行步骤时间线控件。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from smartaccess_v2.runtime.domain.run_session import RunSession


class TimelineTable(QTableWidget):
    """展示运行步骤状态的表格。"""

    HEADERS = ("步骤", "动作", "状态")

    def __init__(self, parent=None) -> None:
        """初始化时间线表格。"""

        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)

    def set_session(self, session: RunSession | None) -> None:
        """显示指定运行会话。

        Args:
            session: 运行会话；为空时清空。
        """

        steps = session.steps if session else []
        self.setRowCount(len(steps))
        for row, step in enumerate(steps):
            values = (step.step_id, step.action, step.status.value)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
                self.setItem(row, column, item)
