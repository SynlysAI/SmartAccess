"""A small colored status badge used across pages (dark, high-contrast)."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QWidget

# (background tint, text color) — text always far brighter than its fill.
_COLORS = {
    "completed": ("#10311f", "#34d399"),
    "succeeded": ("#10311f", "#34d399"),
    "completed_run": ("#10311f", "#34d399"),
    "active": ("#10311f", "#34d399"),
    "published": ("#16315c", "#7eb0ff"),
    "running": ("#16315c", "#7eb0ff"),
    "ready": ("#16315c", "#7eb0ff"),
    "standardized": ("#1f2a4a", "#a5b4fc"),
    "draft": ("#222732", "#c2cad8"),
    "idle": ("#222732", "#c2cad8"),
    "calibrated": ("#33270c", "#fbbf24"),
    "blocked": ("#3a1f0a", "#fb923c"),
    "failed": ("#3a1518", "#f87171"),
    "rolledback": ("#3a1518", "#f87171"),
    "superseded": ("#222732", "#8b94a6"),
}
_DEFAULT = ("#222732", "#c2cad8")


class StatusPill(QLabel):
    """A rounded, colored label reflecting a status string."""

    def __init__(self, status: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        text = status or "-"
        bg, fg = _COLORS.get(text.lower().replace(" ", "").replace(".", "_"), _DEFAULT)
        self.setText(text)
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 9px;"
            " padding: 3px 11px; font-weight: 700;"
        )
