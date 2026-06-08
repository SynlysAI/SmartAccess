"""A scalable screenshot canvas with draggable, resizable ROI rectangles.

Displays a captured window as the background image, with named ROI rectangles
overlaid. Each ROI can be moved and resized via corner handles. The canvas
exports image-space ROI coordinates so calibration persists real anchors.

Colors are tuned for a dark workbench: saturated, high-opacity borders and a
readable text chip on every mask so labels stay legible over any screenshot.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPen,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)
from PyQt6.QtGui import QPixmap

_PLACEHOLDER_W = 640
_PLACEHOLDER_H = 420
# (border, fill) — bright borders, translucent-but-visible fills.
_ROI_COLORS = [
    ("#3b82f6", "#3b82f6"),
    ("#f87171", "#ef4444"),
    ("#34d399", "#10b981"),
    ("#a855f7", "#9333ea"),
    ("#fbbf24", "#f59e0b"),
    ("#22d3ee", "#06b6d4"),
]
_HANDLE = 9.0  # size of resize handles in scene units


class _RoiItem(QGraphicsRectItem):
    """A movable + resizable ROI rectangle with a labeled chip and handles."""

    def __init__(self, name: str, border: str, fill: str, w: float, h: float) -> None:
        super().__init__(QRectF(0, 0, w, h))
        self._name = name
        self._border = QColor(border)
        self._fill = QColor(fill)
        self.setPen(QPen(self._border, 2.2))
        brush = QColor(self._fill)
        brush.setAlpha(70)
        self.setBrush(QBrush(brush))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self.setToolTip(f"{name} · 拖动移动 · 拖角缩放 · 右键删除")

        # Label chip: dark rounded background + bright text, always readable.
        self._chip = QGraphicsRectItem(self)
        self._chip.setBrush(QBrush(QColor(10, 12, 17, 220)))
        self._chip.setPen(QPen(self._border, 1.2))
        self._chip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._label = QGraphicsSimpleTextItem(name, self._chip)
        self._label.setBrush(QBrush(QColor("#f3f6fc")))
        self._label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._position_chip()

        self._resizing = False
        self._active_handle: str | None = None

    # --- geometry helpers --------------------------------------------- #
    def _position_chip(self) -> None:
        text_rect = self._label.boundingRect()
        pad = 4.0
        self._chip.setRect(0, 0, text_rect.width() + pad * 2, text_rect.height() + pad)
        self._label.setPos(pad, pad / 2)
        self._chip.setPos(2, 2)

    def _handle_rects(self) -> dict[str, QRectF]:
        r = self.rect()
        s = _HANDLE
        return {
            "tl": QRectF(r.left() - s / 2, r.top() - s / 2, s, s),
            "tr": QRectF(r.right() - s / 2, r.top() - s / 2, s, s),
            "bl": QRectF(r.left() - s / 2, r.bottom() - s / 2, s, s),
            "br": QRectF(r.right() - s / 2, r.bottom() - s / 2, s, s),
        }

    def paint(self, painter, option, widget=None) -> None:  # noqa: D102
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setBrush(QBrush(self._border))
            painter.setPen(QPen(QColor("#0a0c11"), 1))
            for rect in self._handle_rects().values():
                painter.drawRect(rect)

    # --- mouse: resize when a handle is grabbed ----------------------- #
    def hoverMoveEvent(self, event):  # noqa: N802
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
        self._active_handle = self._handle_at(event.pos())
        if self._active_handle:
            self._resizing = True
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._resizing and self._active_handle:
            self._resize_to(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._resizing = False
        self._active_handle = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        super().mouseReleaseEvent(event)

    def _handle_at(self, pos: QPointF) -> str | None:
        for name, rect in self._handle_rects().items():
            if rect.contains(pos):
                return name
        return None

    def _resize_to(self, pos: QPointF) -> None:
        r = self.rect()
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
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
    """Displays a window screenshot as background with editable ROI rectangles."""

    roi_deleted = pyqtSignal(str)
    roi_added = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)
        self.setRenderHints(self.renderHints())
        self.setBackgroundBrush(QBrush(QColor("#0a0c11")))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._image_item: QGraphicsPixmapItem | None = None
        self._placeholder: QGraphicsRectItem | None = None
        self._error_label: QGraphicsSimpleTextItem | None = None
        self._rois: dict[str, _RoiItem] = {}
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
            rect.setZValue(1)

    def load_placeholder(self, message: str) -> None:
        """Show a frame with ``message`` when no image is available."""

        self._clear_background()
        self._show_placeholder(message)

    def source_size(self) -> tuple[int, int]:
        return self._source_size

    def add_roi(self, name: str, x: float = 48, y: float = 64, w: float = 180, h: float = 80) -> str:
        """Create a named draggable + resizable ROI rectangle and return the name."""

        if name in self._rois:
            return name
        border, fill = _ROI_COLORS[self._color_idx % len(_ROI_COLORS)]
        self._color_idx += 1
        rect = _RoiItem(name, border, fill, w, h)
        rect.setPos(x, y)
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
            if isinstance(item, _RoiItem):
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
            QPen(QColor("#39414f")),
            QBrush(QColor("#13161d")),
        )
        frame.setZValue(-1)
        self._placeholder = frame
        text = self._scene.addSimpleText(message)
        text.setBrush(QBrush(QColor("#8b94a6")))
        text.setFont(QFont("Segoe UI", 11))
        text.setPos(20, _PLACEHOLDER_H / 2 - 12)
        self._error_label = text
        self._scene.setSceneRect(QRectF(0, 0, _PLACEHOLDER_W, _PLACEHOLDER_H))
