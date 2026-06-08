"""A scalable screenshot canvas with draggable ROI rectangles.

Displays a captured window as the background image, with named ROI rectangles
overlaid. The canvas exports image-space ROI coordinates so calibration can
persist real anchors instead of only ROI names.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

_PLACEHOLDER_W = 640
_PLACEHOLDER_H = 420
_ROI_COLORS = [
    ("#2563eb", "#3b82f6", 40),
    ("#dc2626", "#ef4444", 40),
    ("#16a34a", "#22c55e", 40),
    ("#9333ea", "#a855f7", 40),
    ("#ea580c", "#f97316", 40),
    ("#0891b2", "#06b6d4", 40),
]


class RoiCanvas(QGraphicsView):
    """Displays a window screenshot as background with movable ROI rectangles."""

    roi_deleted = pyqtSignal(str)
    roi_added = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self._image_item: QGraphicsPixmapItem | None = None
        self._placeholder: QGraphicsRectItem | None = None
        self._error_label: QGraphicsSimpleTextItem | None = None
        self._rois: dict[str, QGraphicsRectItem] = {}
        self._color_idx = 0
        self._source_size = (_PLACEHOLDER_W, _PLACEHOLDER_H)
        self._show_placeholder("点击「扫描窗口」→ 选择窗口 → 点击「捕获窗口画面」")

    def load_image(self, data: bytes) -> None:
        """Replace the background with a window screenshot from PNG bytes."""

        self._clear_background()
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._show_placeholder("无法解码截图数据，请重试")
            return
        self._image_item = self._scene.addPixmap(pixmap)
        self._image_item.setZValue(-2)
        w = pixmap.width()
        h = pixmap.height()
        self._source_size = (w, h)
        self._scene.setSceneRect(QRectF(0, 0, w, h))
        self.fitInView(QRectF(0, 0, w, h), Qt.AspectRatioMode.KeepAspectRatio)
        for rect in self._rois.values():
            rect.setZValue(0)

    def load_placeholder(self, message: str) -> None:
        """Show a grey frame with ``message`` when no image is available."""

        self._clear_background()
        self._show_placeholder(message)

    def source_size(self) -> tuple[int, int]:
        return self._source_size

    def add_roi(self, name: str, x: float = 40, y: float = 60, w: float = 160, h: float = 70) -> str:
        """Create a named draggable ROI rectangle and return the name."""

        if name in self._rois:
            return name
        border, fill, alpha = _ROI_COLORS[self._color_idx % len(_ROI_COLORS)]
        self._color_idx += 1

        rect = QGraphicsRectItem(QRectF(0, 0, w, h))
        rect.setPos(x, y)
        rect.setPen(QPen(QColor(border), 2))
        rect.setBrush(QBrush(QColor(fill)))
        rect.setOpacity(alpha / 255.0)
        rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        rect.setZValue(1)
        rect.setToolTip(f"右键删除 | {name}")

        label = QGraphicsSimpleTextItem(name, rect)
        label.setBrush(QBrush(QColor("#0f172a")))
        label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        label.setPos(8, 4)
        label.setZValue(2)
        label.setFlag(
            QGraphicsRectItem.GraphicsItemFlag.ItemIgnoresTransformations, True
        )

        self._scene.addItem(rect)
        self._rois[name] = rect
        self.roi_added.emit(name)
        return name

    def remove_roi(self, name: str, *, emit_signal: bool = False) -> None:
        rect = self._rois.pop(name, None)
        if rect is not None:
            self._scene.removeItem(rect)
            if emit_signal:
                self.roi_deleted.emit(name)

    def roi_names(self) -> list[str]:
        return list(self._rois.keys())

    def roi_rect(self, name: str) -> dict[str, float] | None:
        rect = self._rois.get(name)
        if rect is None:
            return None
        bounds = rect.rect()
        pos = rect.pos()
        return {
            "x": max(0.0, float(pos.x() + bounds.x())),
            "y": max(0.0, float(pos.y() + bounds.y())),
            "width": max(0.0, float(bounds.width())),
            "height": max(0.0, float(bounds.height())),
        }

    def normalized_roi_rect(self, name: str) -> dict[str, float] | None:
        rect = self.roi_rect(name)
        if rect is None:
            return None
        source_w, source_h = self._source_size
        if source_w <= 0 or source_h <= 0:
            return None
        return {
            "x": min(1.0, rect["x"] / source_w),
            "y": min(1.0, rect["y"] / source_h),
            "width": min(1.0, rect["width"] / source_w),
            "height": min(1.0, rect["height"] / source_h),
        }

    def roi_rects(self) -> dict[str, dict[str, float]]:
        return {name: rect for name in self._rois if (rect := self.roi_rect(name)) is not None}

    def clear_rois(self) -> None:
        for rect in self._rois.values():
            self._scene.removeItem(rect)
        self._rois.clear()
        self._color_idx = 0

    def clear_all(self) -> None:
        """Remove background image and all ROIs, show placeholder."""

        self._clear_background()
        self.clear_rois()
        self._show_placeholder("点击「扫描窗口」→ 选择窗口 → 点击「捕获窗口画面」")

    def contextMenuEvent(self, event):  # noqa: N802
        """Right-click on an ROI to delete it."""

        item = self.itemAt(event.pos())
        rect_item = self._find_roi_item(item)
        if rect_item is None:
            return
        for name, rect in list(self._rois.items()):
            if rect is rect_item:
                self.remove_roi(name, emit_signal=True)
                return

    def wheelEvent(self, event):  # noqa: N802
        """Ctrl+scroll to zoom."""

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def _find_roi_item(self, item):
        while item is not None:
            if isinstance(item, QGraphicsRectItem) and item in self._rois.values():
                return item
            item = item.parentItem()
        return None

    def _clear_background(self) -> None:
        if self._image_item is not None:
            self._scene.removeItem(self._image_item)
            self._image_item = None
        if self._placeholder is not None:
            self._scene.removeItem(self._placeholder)
            self._placeholder = None
        if self._error_label is not None:
            self._scene.removeItem(self._error_label)
            self._error_label = None

    def _show_placeholder(self, message: str) -> None:
        self._source_size = (_PLACEHOLDER_W, _PLACEHOLDER_H)
        frame = self._scene.addRect(
            QRectF(0, 0, _PLACEHOLDER_W, _PLACEHOLDER_H),
            QPen(QColor("#cbd5e1")),
            QBrush(QColor("#eef2f7")),
        )
        frame.setZValue(-1)
        self._placeholder = frame
        text = self._scene.addSimpleText(message)
        text.setBrush(QBrush(QColor("#64748b")))
        text.setFont(QFont("Segoe UI", 11))
        text.setPos(20, _PLACEHOLDER_H / 2 - 12)
        self._error_label = text
        self._scene.setSceneRect(QRectF(0, 0, _PLACEHOLDER_W, _PLACEHOLDER_H))
