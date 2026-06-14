"""桌面端表格样式工具。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QComboBox,
    QDoubleSpinBox,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QWidget,
)


class NoWheelComboBox(QComboBox):
    """禁用悬停滚轮切换选项的下拉框。"""

    def wheelEvent(self, event) -> None:  # noqa: N802
        """忽略滚轮事件，交给外层滚动区域处理。

        Args:
            event: Qt 滚轮事件。
        """

        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """禁用悬停滚轮修改数值的数字输入框。"""

    def wheelEvent(self, event) -> None:  # noqa: N802
        """忽略滚轮事件，避免误触修改参数。

        Args:
            event: Qt 滚轮事件。
        """

        event.ignore()


def configure_data_table(
    table: QTableWidget,
    *,
    row_height: int = 42,
    stretch_last: bool = False,
) -> None:
    """应用统一数据表格表现层设置。

    Args:
        table: 需要设置的数据表格。
        row_height: 默认行高。
        stretch_last: 是否拉伸最后一列。
    """

    table.setObjectName("DataTable")
    table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    table.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Expanding,
    )
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.verticalHeader().setMinimumSectionSize(row_height)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignVCenter)
    table.horizontalHeader().setStretchLastSection(stretch_last)


def set_embedded_editor_height(widget: QWidget, *, height: int = 32) -> None:
    """设置表格内嵌编辑控件高度。

    Args:
        widget: 表格内嵌控件。
        height: 控件最小高度。
    """

    widget.setMinimumHeight(height)


def interactive_header(table: QTableWidget) -> QHeaderView:
    """返回表格水平表头并设置交互式列宽。

    Args:
        table: 目标表格。

    Returns:
        已设置为交互式列宽的水平表头。
    """

    header = table.horizontalHeader()
    for column in range(table.columnCount()):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
    return header
