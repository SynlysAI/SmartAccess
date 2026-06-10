"""Strong-visual workflow journey graph for the landing page."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from smartaccess.desktop.journey_projection import JourneyProjection, JourneyStageProjection
from smartaccess.desktop.shell import theme as t


@dataclass(frozen=True, slots=True)
class _StageGeometry:
    stage_id: str
    circle: QRectF
    card: QRectF


_COLORS = {
    "completed": (QColor(t.SUCCESS), QColor("#10311f")),
    "current": (QColor(t.PRIMARY_HOVER), QColor(t.PRIMARY_SOFT)),
    "blocked": (QColor("#fb923c"), QColor("#3a1f0a")),
    "future": (QColor(t.INK_SUBTLE), QColor(t.SURFACE_2)),
}


class WorkflowJourneyGraph(QWidget):
    """A horizontal, high-contrast workflow graph with clickable stages."""

    _CANVAS_PADDING_X = 32.0
    _CANVAS_PADDING_Y = 26.0
    _CIRCLE_TOP = 46.0
    _CIRCLE_SIZE = 78.0
    _CARD_TOP = 156.0
    _CARD_WIDTH = 212.0
    _CARD_HEIGHT = 116.0
    _CARD_GAP = 48.0

    stage_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._projection: JourneyProjection | None = None
        self._logical_geometries: list[_StageGeometry] = []
        self._geometries: list[_StageGeometry] = []
        self._layout_origin = QPointF()
        self._layout_scale = 1.0
        self._hovered_stage_id = ""
        self.setMouseTracking(True)
        self.setMinimumHeight(320)

    def set_projection(self, projection: JourneyProjection) -> None:
        self._projection = projection
        self.update()

    def projection(self) -> JourneyProjection | None:
        return self._projection

    def stage_at(self, point: QPointF) -> str:
        for geometry in self._geometries:
            if geometry.circle.contains(point) or geometry.card.contains(point):
                return geometry.stage_id
        return ""

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        stage_id = self.stage_at(event.position())
        if stage_id != self._hovered_stage_id:
            self._hovered_stage_id = stage_id
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if stage_id else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hovered_stage_id:
            self._hovered_stage_id = ""
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            stage_id = self.stage_at(event.position())
            if stage_id:
                self.stage_clicked.emit(stage_id)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(t.CANVAS))

        if self._projection is None or not self._projection.stages:
            self._draw_empty(painter)
            return

        (
            self._logical_geometries,
            self._geometries,
            self._layout_origin,
            self._layout_scale,
        ) = self._compute_geometries(self._projection.stages)

        painter.save()
        painter.translate(self._layout_origin)
        painter.scale(self._layout_scale, self._layout_scale)
        self._draw_connectors(painter, self._logical_geometries)
        for stage, geometry in zip(self._projection.stages, self._logical_geometries, strict=True):
            self._draw_stage(painter, stage, geometry)
        painter.restore()

    def _compute_geometries(
        self,
        stages: list[JourneyStageProjection],
    ) -> tuple[list[_StageGeometry], list[_StageGeometry], QPointF, float]:
        if not stages:
            return [], [], QPointF(), 1.0

        count = len(stages)
        step = self._CARD_WIDTH + self._CARD_GAP
        content_width = self._CARD_WIDTH * count + self._CARD_GAP * (count - 1)
        content_height = self._CARD_TOP + self._CARD_HEIGHT
        available_width = max(self.width() - self._CANVAS_PADDING_X * 2, 1.0)
        available_height = max(self.height() - self._CANVAS_PADDING_Y * 2, 1.0)
        scale = min(available_width / content_width, available_height / content_height)
        origin = QPointF(
            (self.width() - content_width * scale) / 2,
            (self.height() - content_height * scale) / 2,
        )

        logical_geometries: list[_StageGeometry] = []
        actual_geometries: list[_StageGeometry] = []
        for index, stage in enumerate(stages):
            center_x = self._CARD_WIDTH / 2 + index * step
            circle = QRectF(
                center_x - self._CIRCLE_SIZE / 2,
                self._CIRCLE_TOP,
                self._CIRCLE_SIZE,
                self._CIRCLE_SIZE,
            )
            card = QRectF(
                center_x - self._CARD_WIDTH / 2,
                self._CARD_TOP,
                self._CARD_WIDTH,
                self._CARD_HEIGHT,
            )
            logical_geometries.append(_StageGeometry(stage.stage_id, circle, card))
            actual_geometries.append(
                _StageGeometry(
                    stage.stage_id,
                    self._map_rect(circle, origin, scale),
                    self._map_rect(card, origin, scale),
                )
            )
        return logical_geometries, actual_geometries, origin, scale

    def _draw_connectors(self, painter: QPainter, geometries: list[_StageGeometry]) -> None:
        if len(geometries) < 2:
            return
        pen = QPen(QColor(t.HAIRLINE_STRONG), 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        for left, right in zip(geometries, geometries[1:], strict=False):
            start = QPointF(left.circle.right() - 4, left.circle.center().y())
            end = QPointF(right.circle.left() + 4, right.circle.center().y())
            painter.drawLine(start, end)

    def _draw_stage(self, painter: QPainter, stage: JourneyStageProjection, geometry: _StageGeometry) -> None:
        fg, bg = _COLORS[stage.status]
        hovered = stage.stage_id == self._hovered_stage_id

        shadow_color = QColor(fg)
        shadow_color.setAlpha(120 if stage.status in {"current", "blocked"} else 55)
        shadow_rect = geometry.circle.adjusted(-12, -12, 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow_color)
        painter.drawEllipse(shadow_rect)

        circle_pen = QPen(fg, 3 if hovered else 2)
        painter.setPen(circle_pen)
        painter.setBrush(QColor(t.SURFACE_1))
        painter.drawEllipse(geometry.circle)

        inner = geometry.circle.adjusted(10, 10, -10, -10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg if stage.status != "future" else QColor(t.SURFACE_2))
        painter.drawEllipse(inner)

        painter.setPen(fg)
        painter.setFont(self._font(18, 700))
        painter.drawText(geometry.circle, Qt.AlignmentFlag.AlignCenter, str(self._stage_number(stage.stage_id)))

        card_path = QPainterPath()
        card_path.addRoundedRect(geometry.card, 18, 18)
        card_fill = QColor(t.SURFACE_1)
        if hovered:
            card_fill = QColor(t.SURFACE_2)
        painter.fillPath(card_path, card_fill)
        card_pen = QPen(fg if stage.status in {"current", "blocked"} else QColor(t.HAIRLINE_STRONG), 1.5)
        painter.setPen(card_pen)
        painter.drawPath(card_path)

        text_rect = geometry.card.adjusted(16, 14, -16, -14)
        painter.setPen(QColor(t.INK))
        painter.setFont(self._font(13, 700))
        painter.drawText(
            QRectF(text_rect.left(), text_rect.top(), text_rect.width(), 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            stage.title,
        )

        meta_color = fg if stage.status != "future" else QColor(t.INK_MUTED)
        painter.setPen(meta_color)
        painter.setFont(self._font(11, 600))
        painter.drawText(
            QRectF(text_rect.left(), text_rect.top() + 28, text_rect.width(), 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            stage.meta,
        )

        painter.setPen(QColor(t.INK_MUTED))
        painter.setFont(self._font(10, 500))
        painter.drawText(
            QRectF(text_rect.left(), text_rect.top() + 52, text_rect.width(), 34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            stage.description,
        )

        badge_rect = QRectF(text_rect.left(), geometry.card.bottom() - 34, 84, 22)
        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 11, 11)
        painter.fillPath(badge_path, bg if stage.status != "future" else QColor(t.SURFACE_3))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(meta_color)
        painter.setFont(self._font(10, 700))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._status_text(stage.status))

    def _draw_empty(self, painter: QPainter) -> None:
        painter.setPen(QColor(t.INK_SUBTLE))
        painter.setFont(self._font(14, 500))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无流程数据")

    @staticmethod
    def _stage_number(stage_id: str) -> int:
        mapping = {
            "calibration": 1,
            "workflow": 2,
            "template": 3,
            "monitoring": 4,
        }
        return mapping.get(stage_id, 0)

    @staticmethod
    def _status_text(status: str) -> str:
        return {
            "completed": "已完成",
            "current": "当前步骤",
            "blocked": "有阻塞",
            "future": "后续",
        }.get(status, status)

    @staticmethod
    def _font(size: int, weight: int | QFont.Weight) -> QFont:
        font = QFont("Segoe UI")
        font.setPointSize(max(1, int(size)))
        if isinstance(weight, QFont.Weight):
            font.setWeight(weight)
        elif weight >= 700:
            font.setWeight(QFont.Weight.Bold)
        elif weight >= 600:
            font.setWeight(QFont.Weight.DemiBold)
        elif weight >= 500:
            font.setWeight(QFont.Weight.Medium)
        else:
            font.setWeight(QFont.Weight.Normal)
        return font

    @staticmethod
    def _map_rect(rect: QRectF, origin: QPointF, scale: float) -> QRectF:
        return QRectF(
            origin.x() + rect.x() * scale,
            origin.y() + rect.y() * scale,
            rect.width() * scale,
            rect.height() * scale,
        )
