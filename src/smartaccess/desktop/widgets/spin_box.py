"""桌面端统一数字输入框控件。"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QColor, QPainter, QPolygon
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QSpinBox,
    QStyle,
    QStyleOptionSpinBox,
    QWidget,
)


class FocusWheelDoubleSpinBox(QDoubleSpinBox):
    """仅在鼠标点击激活后响应滚轮的浮点数字输入框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化浮点数字输入框。

        Args:
            parent: Qt 父组件。
        """

        super().__init__(parent)
        self._wheel_activated = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """监听内部文本编辑器的点击和失焦事件。

        Args:
            watched: 当前接收事件的对象。
            event: Qt 输入事件。

        Returns:
            是否已拦截当前事件。
        """

        if watched is self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress:
                self._wheel_activated = True
            elif event.type() == QEvent.Type.FocusOut:
                self._wheel_activated = False
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """通过鼠标点击激活当前输入框的滚轮调整。

        Args:
            event: Qt 鼠标点击事件。
        """

        self._wheel_activated = True
        super().mousePressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        """输入框失去焦点时关闭滚轮调整。

        Args:
            event: Qt 焦点事件。
        """

        self._wheel_activated = False
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制输入框并补充清晰的上下箭头。

        Args:
            event: Qt 绘制事件。
        """

        super().paintEvent(event)
        _paint_spin_arrows(self)

    def wheelEvent(self, event) -> None:  # noqa: N802
        """仅在鼠标点击激活后处理滚轮事件。

        Args:
            event: Qt 滚轮事件。
        """

        if self._wheel_activated and self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()


class FocusWheelSpinBox(QSpinBox):
    """仅在鼠标点击激活后响应滚轮的整数输入框。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化整数输入框。

        Args:
            parent: Qt 父组件。
        """

        super().__init__(parent)
        self._wheel_activated = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """监听内部文本编辑器的点击和失焦事件。

        Args:
            watched: 当前接收事件的对象。
            event: Qt 输入事件。

        Returns:
            是否已拦截当前事件。
        """

        if watched is self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress:
                self._wheel_activated = True
            elif event.type() == QEvent.Type.FocusOut:
                self._wheel_activated = False
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """通过鼠标点击激活当前输入框的滚轮调整。

        Args:
            event: Qt 鼠标点击事件。
        """

        self._wheel_activated = True
        super().mousePressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        """输入框失去焦点时关闭滚轮调整。

        Args:
            event: Qt 焦点事件。
        """

        self._wheel_activated = False
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        """绘制输入框并补充清晰的上下箭头。

        Args:
            event: Qt 绘制事件。
        """

        super().paintEvent(event)
        _paint_spin_arrows(self)

    def wheelEvent(self, event) -> None:  # noqa: N802
        """仅在鼠标点击激活后处理滚轮事件。

        Args:
            event: Qt 滚轮事件。
        """

        if self._wheel_activated and self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()


def _paint_spin_arrows(spin: QSpinBox | QDoubleSpinBox) -> None:
    """在数字输入框按钮区域绘制上下箭头。

    Args:
        spin: 需要绘制箭头的数字输入框。
    """

    option = QStyleOptionSpinBox()
    spin.initStyleOption(option)
    up_rect = spin.style().subControlRect(
        QStyle.ComplexControl.CC_SpinBox,
        option,
        QStyle.SubControl.SC_SpinBoxUp,
        spin,
    )
    down_rect = spin.style().subControlRect(
        QStyle.ComplexControl.CC_SpinBox,
        option,
        QStyle.SubControl.SC_SpinBoxDown,
        spin,
    )
    painter = QPainter(spin)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#4B5B73"))
    up_center = up_rect.center()
    painter.drawPolygon(
        QPolygon(
            [
                QPoint(up_center.x() - 4, up_center.y() + 3),
                QPoint(up_center.x() + 4, up_center.y() + 3),
                QPoint(up_center.x(), up_center.y() - 3),
            ]
        )
    )
    down_center = down_rect.center()
    painter.drawPolygon(
        QPolygon(
            [
                QPoint(down_center.x() - 4, down_center.y() - 3),
                QPoint(down_center.x() + 4, down_center.y() - 3),
                QPoint(down_center.x(), down_center.y() + 3),
            ]
        )
    )
    painter.end()
