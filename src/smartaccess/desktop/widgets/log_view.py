"""A streaming, read-only log view."""

from __future__ import annotations

from PyQt6.QtWidgets import QPlainTextEdit, QWidget


class LogView(QPlainTextEdit):
    """Append-only log panel with a bounded backlog."""

    def __init__(self, parent: QWidget | None = None, max_lines: int = 500) -> None:
        super().__init__(parent)
        self.setObjectName("LogView")
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)

    def append_line(self, text: str) -> None:
        self.appendPlainText(text)
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self) -> None:
        self.clear()
