"""A wrapped, color-coded step timeline for the monitoring page."""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.shell import theme as t

_ICON = {
    "pending": "○",
    "running": "◉",
    "observed": "◌",
    "succeeded": "●",
    "blocked": "▲",
    "failed": "✕",
}
_COLOR = {
    "pending": t.INK_SUBTLE,
    "running": t.PRIMARY_HOVER,
    "observed": t.PRIMARY_HOVER,
    "succeeded": t.SUCCESS,
    "blocked": t.WARNING,
    "failed": t.DANGER,
}
_LABEL = {
    "pending": "Pending",
    "running": "Running",
    "observed": "Observed",
    "succeeded": "Succeeded",
    "blocked": "Blocked",
    "failed": "Failed",
}


def _format_value(action: str, value: str) -> str:
    if not value:
        return "-"
    if action == "wait":
        return f"{value}s"
    return value


class _TimelineRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._title)

        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._detail)

    def update_row(
        self,
        *,
        index: int,
        step_id: str,
        action: str,
        anchor_id: str,
        value: str,
        status: str,
        status_time: str = "",
    ) -> None:
        color = _COLOR.get(status, t.INK_MUTED)
        icon = _ICON.get(status, "○")
        label = _LABEL.get(status, status.title())
        title = (
            f"<span style='color:{color};font-weight:700;'>{icon}</span> "
            f"<span style='font-weight:700;color:{t.INK};'>{index}. "
            f"{html.escape(step_id)}</span> "
            f"<span style='color:{color};'>[{html.escape(action or '-')} · {label}]</span>"
        )
        if status_time:
            title += (
                f" <span style='color:{t.INK_SUBTLE};'>at {html.escape(status_time)}</span>"
            )
        detail = (
            f"<span style='color:{t.INK_MUTED};'><b>anchor_id</b>: {html.escape(anchor_id or '-')}<br>"
            f"<b>Value</b>: {html.escape(_format_value(action, value))}</span>"
        )
        self._title.setText(title)
        self._detail.setText(detail)


class Timeline(QListWidget):
    """Shows ordered steps with wrapping detail rows and live status."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, QListWidgetItem] = {}
        self._widgets: dict[str, _TimelineRow] = {}
        self._meta: dict[str, dict[str, str]] = {}
        self.setWordWrap(True)
        self.setUniformItemSizes(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(6)

    def reset_steps(self, steps: list[dict]) -> None:
        self.clear()
        self._rows.clear()
        self._widgets.clear()
        self._meta.clear()
        for index, step in enumerate(steps, start=1):
            step_id = step.get("id", f"step_{index}")
            meta = {
                "action": str(step.get("action", "")),
                "anchor_id": str(step.get("anchor_id", "") or ""),
                "value": str(step.get("value", "") or ""),
                "status": "pending",
                "status_time": "",
            }
            self._meta[step_id] = meta
            item = QListWidgetItem()
            widget = _TimelineRow()
            self.addItem(item)
            self.setItemWidget(item, widget)
            self._rows[step_id] = item
            self._widgets[step_id] = widget
            self._refresh_row(step_id, index=index)

    def set_step_status(self, step_id: str, status: str, status_time: str = "") -> None:
        if step_id not in self._rows:
            item = QListWidgetItem()
            widget = _TimelineRow()
            self.addItem(item)
            self.setItemWidget(item, widget)
            self._rows[step_id] = item
            self._widgets[step_id] = widget
            self._meta[step_id] = {
                "action": "",
                "anchor_id": "",
                "value": "",
                "status": status,
                "status_time": status_time,
            }
        meta = self._meta.setdefault(
            step_id,
            {
                "action": "",
                "anchor_id": "",
                "value": "",
                "status": status,
                "status_time": "",
            },
        )
        meta["status"] = status
        if status_time:
            meta["status_time"] = status_time
        self._refresh_row(step_id)

    def _refresh_row(self, step_id: str, *, index: int | None = None) -> None:
        item = self._rows[step_id]
        widget = self._widgets[step_id]
        meta = self._meta[step_id]
        row_index = index if index is not None else list(self._rows).index(step_id) + 1
        widget.setFixedWidth(max(120, self.viewport().width() - 12))
        widget.update_row(
            index=row_index,
            step_id=step_id,
            action=meta.get("action", ""),
            anchor_id=meta.get("anchor_id", ""),
            value=meta.get("value", ""),
            status=meta.get("status", "pending"),
            status_time=meta.get("status_time", ""),
        )
        item.setSizeHint(widget.sizeHint())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        for step_id in list(self._rows):
            self._refresh_row(step_id)
