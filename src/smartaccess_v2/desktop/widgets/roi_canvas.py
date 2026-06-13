"""可缩放、可拖拽的 ROI 截图画布。"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

PLACEHOLDER_WIDTH = 640
PLACEHOLDER_HEIGHT = 420
HANDLE_SIZE = 9.0
ROI_COLORS = [
    ("#1f6fd6", "#1f6fd6"),
    ("#c53030", "#e05252"),
    ("#0f9f6e", "#10b981"),
    ("#7c3aed", "#8b5cf6"),
    ("#c77900", "#f59e0b"),
    ("#0284c7", "#38bdf8"),
]


class _RoiItem(QGraphicsRectItem):
    """画布中的一个可移动、可缩放 ROI。"""

    def __init__(self, name: str, border: str, fill: str, width: float, height: float) -> None:
        """初始化 ROI 图元。

        Args:
            name: ROI 名称。
            border: 边框颜色。
            fill: 填充颜色。
            width: 初始宽度。
            height: 初始高度。
        """

        super().__init__(QRectF(0, 0, width, height))
        self.name = name
        self._border = QColor(border)
        fill_color = QColor(fill)
        fill_color.setAlpha(45)
        self.setPen(QPen(self._border, 2.0))
        self.setBrush(QBrush(fill_color))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self.setToolTip(f"{name} · 拖动移动 · 拖角缩放 · 右键删除")

        self._chip = QGraphicsRectItem(self)
        self._chip.setBrush(QBrush(QColor(255, 255, 255, 235)))
        self._chip.setPen(QPen(self._border, 1.0))
        self._chip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._label = QGraphicsSimpleTextItem(name, self._chip)
        self._label.setBrush(QBrush(QColor("#172033")))
        self._label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._position_chip()

        self._resizing = False
        self._active_handle: str | None = None

    def itemChange(self, change, value):  # noqa: N802
        """ROI 位置改变时通知画布。"""

        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            parent = scene.parent() if scene is not None else None
            if isinstance(parent, RoiCanvas):
                parent.notify_roi_changed(self.name)
        return result

    def paint(self, painter, option, widget=None) -> None:  # noqa: D102
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setBrush(QBrush(self._border))
            painter.setPen(QPen(QColor("#ffffff"), 1))
            for rect in self._handle_rects().values():
                painter.drawRect(rect)

    def hoverMoveEvent(self, event):  # noqa: N802
        """根据鼠标所在位置切换光标。"""

        handle = self._handle_at(event.pos())
        cursors = {
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(handle, Qt.CursorShape.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        """按下拖拽角点时进入缩放模式。"""

        self._active_handle = self._handle_at(event.pos())
        if self._active_handle:
            self._resizing = True
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        """拖拽时移动或缩放 ROI。"""

        if self._resizing and self._active_handle:
            self._resize_to(event.pos())
            scene = self.scene()
            parent = scene.parent() if scene is not None else None
            if isinstance(parent, RoiCanvas):
                parent.notify_roi_changed(self.name)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        """释放鼠标时退出缩放模式。"""

        self._resizing = False
        self._active_handle = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        scene = self.scene()
        parent = scene.parent() if scene is not None else None
        if isinstance(parent, RoiCanvas):
            parent.notify_roi_changed(self.name)
        super().mouseReleaseEvent(event)

    def _position_chip(self) -> None:
        """调整标签位置。"""

        text_rect = self._label.boundingRect()
        pad = 4.0
        self._chip.setRect(0, 0, text_rect.width() + pad * 2, text_rect.height() + pad)
        self._label.setPos(pad, pad / 2)
        self._chip.setPos(2, 2)

    def _handle_rects(self) -> dict[str, QRectF]:
        """返回四个缩放手柄区域。"""

        rect = self.rect()
        size = HANDLE_SIZE
        return {
            "tl": QRectF(rect.left() - size / 2, rect.top() - size / 2, size, size),
            "tr": QRectF(rect.right() - size / 2, rect.top() - size / 2, size, size),
            "bl": QRectF(rect.left() - size / 2, rect.bottom() - size / 2, size, size),
            "br": QRectF(rect.right() - size / 2, rect.bottom() - size / 2, size, size),
        }

    def _handle_at(self, pos: QPointF) -> str | None:
        """返回鼠标命中的手柄名。"""

        for name, rect in self._handle_rects().items():
            if rect.contains(pos):
                return name
        return None

    def _resize_to(self, pos: QPointF) -> None:
        """根据鼠标位置缩放 ROI。"""

        rect = self.rect()
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        if "l" in self._active_handle:
            left = min(pos.x(), right - 12)
        if "r" in self._active_handle:
            right = max(pos.x(), left + 12)
        if "t" in self._active_handle:
            top = min(pos.y(), bottom - 12)
        if "b" in self._active_handle:
            bottom = max(pos.y(), top + 12)
        self.prepareGeometryChange()
        self.setRect(QRectF(left, top, right - left, bottom - top))
        self._position_chip()


class RoiCanvas(QGraphicsView):
    """显示截图并编辑 ROI 的画布。"""

    roi_added = pyqtSignal(str)
    roi_removed = pyqtSignal(str)
    roi_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化 ROI 画布。"""

        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)
        self.setObjectName("RoiCanvas")
        self._scene.setParent(self)
        self.setBackgroundBrush(QBrush(QColor("#F0F3F8")))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._image_item: QGraphicsPixmapItem | None = None
        self._placeholder: QGraphicsRectItem | None = None
        self._placeholder_text: QGraphicsSimpleTextItem | None = None
        self._rois: dict[str, _RoiItem] = {}
        self._color_index = 0
        self._source_size = (PLACEHOLDER_WIDTH, PLACEHOLDER_HEIGHT)
        self._show_placeholder("扫描窗口并捕获截图后，在此编辑 ROI")

    def load_image(self, data: bytes) -> None:
        """加载截图背景。

        Args:
            data: PNG 截图字节。
        """

        self._clear_background()
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._show_placeholder("无法解码截图数据")
            return
        self._image_item = self._scene.addPixmap(pixmap)
        self._image_item.setZValue(-2)
        self._source_size = (pixmap.width(), pixmap.height())
        rect = QRectF(0, 0, pixmap.width(), pixmap.height())
        self._scene.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def load_placeholder(self, message: str) -> None:
        """显示占位提示。"""

        self._clear_background()
        self._show_placeholder(message)

    def source_size(self) -> tuple[int, int]:
        """返回当前截图尺寸。"""

        return self._source_size

    def add_roi(
        self,
        name: str,
        x: float = 48,
        y: float = 64,
        width: float = 180,
        height: float = 80,
    ) -> str:
        """新增 ROI。

        Args:
            name: ROI 名称。
            x: 左上角 X。
            y: 左上角 Y。
            width: 宽度。
            height: 高度。

        Returns:
            ROI 名称。
        """

        if name in self._rois:
            return name
        border, fill = ROI_COLORS[self._color_index % len(ROI_COLORS)]
        self._color_index += 1
        item = _RoiItem(name, border, fill, width, height)
        item.setPos(x, y)
        self._scene.addItem(item)
        self._rois[name] = item
        self.roi_added.emit(name)
        self.roi_changed.emit(name)
        return name

    def remove_roi(self, name: str, *, emit_signal: bool = True) -> None:
        """删除 ROI。"""

        item = self._rois.pop(name, None)
        if item is None:
            return
        self._scene.removeItem(item)
        if emit_signal:
            self.roi_removed.emit(name)

    def clear_rois(self) -> None:
        """清除全部 ROI。"""

        for item in self._rois.values():
            self._scene.removeItem(item)
        self._rois.clear()
        self._color_index = 0

    def clear_all(self) -> None:
        """清除截图和 ROI。"""

        self._clear_background()
        self.clear_rois()
        self._show_placeholder("扫描窗口并捕获截图后，在此编辑 ROI")

    def roi_names(self) -> list[str]:
        """返回所有 ROI 名称。"""

        return list(self._rois.keys())

    def roi_rect(self, name: str) -> dict[str, float] | None:
        """返回 ROI 像素坐标。"""

        item = self._rois.get(name)
        if item is None:
            return None
        bounds = item.rect()
        pos = item.pos()
        return {
            "x": max(0.0, float(pos.x() + bounds.x())),
            "y": max(0.0, float(pos.y() + bounds.y())),
            "width": max(0.0, float(bounds.width())),
            "height": max(0.0, float(bounds.height())),
        }

    def normalized_roi_rect(self, name: str) -> dict[str, float] | None:
        """返回 ROI 归一化坐标。"""

        rect = self.roi_rect(name)
        if rect is None:
            return None
        source_width, source_height = self._source_size
        if source_width <= 0 or source_height <= 0:
            return None
        return {
            "x": min(1.0, rect["x"] / source_width),
            "y": min(1.0, rect["y"] / source_height),
            "width": min(1.0, rect["width"] / source_width),
            "height": min(1.0, rect["height"] / source_height),
        }

    def notify_roi_changed(self, name: str) -> None:
        """由 ROI 图元通知坐标变化。"""

        if name in self._rois:
            self.roi_changed.emit(name)

    def contextMenuEvent(self, event):  # noqa: N802
        """右键删除 ROI。"""

        item = self.itemAt(event.pos())
        roi_item = self._find_roi_item(item)
        if roi_item is None:
            return
        self.remove_roi(roi_item.name, emit_signal=True)

    def wheelEvent(self, event):  # noqa: N802
        """Ctrl + 滚轮缩放画布。"""

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            return
        super().wheelEvent(event)

    @staticmethod
    def _find_roi_item(item) -> _RoiItem | None:
        """从图元树中查找 ROI 图元。"""

        while item is not None:
            if isinstance(item, _RoiItem):
                return item
            item = item.parentItem()
        return None

    def _clear_background(self) -> None:
        """清除背景截图或占位符。"""

        for item_name in ("_image_item", "_placeholder", "_placeholder_text"):
            item = getattr(self, item_name)
            if item is not None:
                self._scene.removeItem(item)
                setattr(self, item_name, None)

    def _show_placeholder(self, message: str) -> None:
        """显示占位提示。"""

        self._source_size = (PLACEHOLDER_WIDTH, PLACEHOLDER_HEIGHT)
        frame = self._scene.addRect(
            QRectF(0, 0, PLACEHOLDER_WIDTH, PLACEHOLDER_HEIGHT),
            QPen(QColor("#c8d2e2")),
            QBrush(QColor("#f8fafc")),
        )
        frame.setZValue(-1)
        self._placeholder = frame
        text = self._scene.addSimpleText(message)
        text.setBrush(QBrush(QColor("#526179")))
        text.setFont(QFont("Segoe UI", 11))
        text.setPos(20, PLACEHOLDER_HEIGHT / 2 - 12)
        self._placeholder_text = text
        self._scene.setSceneRect(QRectF(0, 0, PLACEHOLDER_WIDTH, PLACEHOLDER_HEIGHT))
