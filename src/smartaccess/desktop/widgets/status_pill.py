"""A small colored status badge used across pages."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QWidget

_COLORS = {
    "completed": ("#dcfce7", "#166534"),
    "succeeded": ("#dcfce7", "#166534"),
    "active": ("#dcfce7", "#166534"),
    "published": ("#dbeafe", "#1e40af"),
    "running": ("#dbeafe", "#1e40af"),
    "ready": ("#e0e7ff", "#3730a3"),
    "standardized": ("#e0e7ff", "#3730a3"),
    "draft": ("#f1f5f9", "#475569"),
    "calibrated": ("#fef9c3", "#854d0e"),
    "blocked": ("#fee2e2", "#991b1b"),
    "failed": ("#fee2e2", "#991b1b"),
    "rolledback": ("#fee2e2", "#991b1b"),
    "superseded": ("#f1f5f9", "#475569"),
}
_DEFAULT = ("#f1f5f9", "#475569")


class StatusPill(QLabel):
    """A rounded, colored label reflecting a status string."""

    def __init__(self, status: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        text = status or "-"
        bg, fg = _COLORS.get(text.lower().replace(" ", ""), _DEFAULT)
        self.setText(text)
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 9px;"
            " padding: 2px 10px; font-weight: 600;"
        )
