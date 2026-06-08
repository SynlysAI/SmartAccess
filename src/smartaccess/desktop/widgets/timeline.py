"""A run-step timeline list for the monitoring page (dark, color-coded).

Each row shows the step index, icon, action, target, value, and status label.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QWidget

from smartaccess.desktop.shell import theme as t

_ICON = {
    "pending": "○",
    "running": "◐",
    "observed": "◑",
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
    "pending": "待执行",
    "running": "执行中",
    "observed": "已观测",
    "succeeded": "成功",
    "blocked": "已阻断",
    "failed": "失败",
}


def _format_step_line(
    idx: int, step_id: str, action: str = "", target: str = "", value: str = "", status: str = "pending"
) -> str:
    """Build a plain-text one-line summary for a timeline row.

    Example outputs:
      ○  1. step_1  [click]  → search_box                      · 待执行
      ◐  2. step_2  [type]   → search_box   = "李建置"          · 执行中
      ○  3. step_3  [wait]   = 3s                               · 待执行
      ●  4. step_4  [click]  → contact_item                     · 成功
    """
    icon = _ICON.get(status, "○")
    label = _LABEL.get(status, status)

    # action: [click] / [type] / [wait] — padded to 12 chars for alignment
    action_part = f"[{action}]".ljust(14) if action else ""

    # target: → search_box
    target_part = f" → {target}" if target else ""

    # value: context-aware formatting
    value_part = ""
    if value:
        if action == "wait":
            value_part = f"  = {value}s"
        elif action in ("type", "hotkey"):
            # Truncate long values for display
            display = str(value)
            if len(display) > 32:
                display = display[:29] + "..."
            value_part = f'  = "{display}"'
        else:
            value_part = f"  = {value}"

    # status
    status_part = f"· {label}"

    return f"{icon}  {idx}. {step_id}  {action_part}{target_part}{value_part}  {status_part}"


class Timeline(QListWidget):
    """Shows ordered steps with action / target / value details and live status."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, QListWidgetItem] = {}
        # Store step metadata keyed by step_id for status updates.
        self._meta: dict[str, dict] = {}

    def reset_steps(self, steps: list[dict]) -> None:
        """Accept a list of step dicts with keys: id, action, target, value."""
        print(f"[DEBUG] Timeline.reset_steps called with {len(steps)} steps")
        self.clear()
        self._rows.clear()
        self._meta.clear()
        for idx, step in enumerate(steps, start=1):
            step_id = step.get("id", f"step_{idx}")
            action = step.get("action", "")
            target = step.get("target", "") or ""
            value = str(step.get("value", "")) if step.get("value") is not None else ""
            self._meta[step_id] = {"action": action, "target": target, "value": value}
            text = _format_step_line(idx, step_id, action, target, value, "pending")
            item = QListWidgetItem()
            item.setText(text)
            item.setForeground(QColor(_COLOR["pending"]))
            self.addItem(item)
            self._rows[step_id] = item

    def set_step_status(self, step_id: str, status: str) -> None:
        """Update a step's status icon and label, preserving its detail text."""
        item = self._rows.get(step_id)
        if item is None:
            item = QListWidgetItem()
            self.addItem(item)
            self._rows[step_id] = item
            self._meta[step_id] = {"action": "", "target": "", "value": ""}
        meta = self._meta.get(step_id, {"action": "", "target": "", "value": ""})
        idx = list(self._rows).index(step_id) + 1
        text = _format_step_line(
            idx, step_id,
            action=meta.get("action", ""),
            target=meta.get("target", ""),
            value=meta.get("value", ""),
            status=status,
        )
        item.setText(text)
        item.setForeground(QColor(_COLOR.get(status, t.INK_MUTED)))
