"""A run-step timeline list for the monitoring page."""

from __future__ import annotations

from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget

_ICON = {
    "pending": "○",
    "running": "◐",
    "observed": "◑",
    "succeeded": "●",
    "blocked": "▲",
    "failed": "✕",
}


class Timeline(QListWidget):
    """Shows ordered steps and their current status."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, QListWidgetItem] = {}

    def reset(self, step_ids: list[str]) -> None:
        self.clear()
        self._rows.clear()
        for step_id in step_ids:
            item = QListWidgetItem(f"{_ICON['pending']}  {step_id}")
            self.addItem(item)
            self._rows[step_id] = item

    def set_step_status(self, step_id: str, status: str) -> None:
        item = self._rows.get(step_id)
        icon = _ICON.get(status, "○")
        if item is None:
            item = QListWidgetItem("")
            self.addItem(item)
            self._rows[step_id] = item
        item.setText(f"{icon}  {step_id}  —  {status}")
