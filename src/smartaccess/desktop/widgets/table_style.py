"""桌面端表格样式工具。"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyleOptionComboBox, QStyleOptionSpinBox
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QWidget,
)


class TableCheckBox(QCheckBox):
    """绘制带明确对勾的表格复选框。"""

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        """让整块单元格控件区域都可以响应点击。

        Args:
            pos: 鼠标点击在控件内的位置。

        Returns:
            点击位置是否在可切换区域内。
        """

        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制表格内复选框的勾选和未勾选状态。

        Args:
            event: Qt 绘制事件。
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = 18
        rect = QRect(
            max(0, (self.width() - size) // 2),
            max(0, (self.height() - size) // 2),
            size,
            size,
        )
        if self.isChecked():
            painter.setPen(QPen(QColor("#2563EB"), 1))
            painter.setBrush(QColor("#2563EB"))
        else:
            painter.setPen(QPen(QColor("#CBD5E1"), 1))
            painter.setBrush(QColor("#FFFFFF"))
        if not self.isEnabled():
            painter.setOpacity(0.45)
        painter.drawRoundedRect(rect, 4, 4)
        if self.isChecked():
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawLine(rect.left() + 4, rect.center().y(), rect.left() + 8, rect.bottom() - 5)
            painter.drawLine(rect.left() + 8, rect.bottom() - 5, rect.right() - 4, rect.top() + 5)
        painter.end()


class NoWheelComboBox(QComboBox):
    """禁用悬停滚轮切换选项的下拉框。"""

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制稳定可见的下拉箭头。

        Args:
            event: Qt 绘制事件。
        """

        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option, painter, self)
        arrow_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxArrow,
            self,
        )
        text_rect = QRect(option.rect)
        text_rect.setLeft(text_rect.left() + 10)
        text_rect.setRight(arrow_rect.left() - 6)
        painter.setPen(QColor("#111827"))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.currentText(),
        )
        painter.setPen(QColor("#4B5B73"))
        painter.drawText(arrow_rect, Qt.AlignmentFlag.AlignCenter, "▼")
        painter.end()

    def wheelEvent(self, event) -> None:  # noqa: N802
        """忽略滚轮事件，交给外层滚动区域处理。

        Args:
            event: Qt 滚轮事件。
        """

        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """禁用悬停滚轮修改数值的数字输入框。"""

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制稳定可见的上下调整箭头。

        Args:
            event: Qt 绘制事件。
        """

        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        up_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxUp,
            self,
        )
        down_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxDown,
            self,
        )
        painter.setPen(QColor("#4B5B73"))
        painter.drawText(up_rect, Qt.AlignmentFlag.AlignCenter, "▲")
        painter.drawText(down_rect, Qt.AlignmentFlag.AlignCenter, "▼")
        painter.end()

    def wheelEvent(self, event) -> None:  # noqa: N802
        """忽略滚轮事件，避免误触修改参数。

        Args:
            event: Qt 滚轮事件。
        """

        event.ignore()


def configure_data_table(
    table: QTableWidget,
    *,
    row_height: int = 38,
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


def set_embedded_editor_height(widget: QWidget, *, height: int = 26) -> None:
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
