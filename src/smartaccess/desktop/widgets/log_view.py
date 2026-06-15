"""运行日志控件。"""

from __future__ import annotations

from PyQt6.QtWidgets import QTextEdit

from smartaccess.desktop.shell import theme
from smartaccess.desktop.viewmodels.monitoring_vm import MonitorLogEntry
from smartaccess.desktop.widgets import rich_text


class LogView(QTextEdit):
    """展示运行事件日志。"""

    def __init__(self, parent=None) -> None:
        """初始化日志视图。"""

        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

    def set_entries(self, entries: list[MonitorLogEntry]) -> None:
        """刷新日志内容。

        Args:
            entries: 日志行列表。
        """

        lines = [self._entry_html(entry) for entry in entries[-300:]]
        self.setHtml(rich_text.document("".join(lines)))
        self.moveCursor(self.textCursor().MoveOperation.End)

    @staticmethod
    def _entry_html(entry: MonitorLogEntry) -> str:
        """Render one log entry as HTML."""

        color = {
            "ERROR": theme.DANGER,
            "WARN": theme.WARNING,
            "INFO": theme.TEXT,
        }.get(entry.level, theme.TEXT)
        message = _message_html(entry.message)
        return (
            f"<div style=\"line-height:1.25;margin:0;color:{color};\">"
            f"<span style=\"color:{theme.TEXT_MUTED};\">{rich_text.text(entry.timestamp)}</span> "
            f"<span style=\"color:{color};font-weight:700;\">[{rich_text.text(entry.level)}]</span>"
            f"<div style=\"margin:0 0 0 10px;overflow-wrap:anywhere;word-break:break-all;\">"
            f"{message}</div>"
            "</div>"
        )


def _message_html(message: str) -> str:
    """Render a log message, splitting OCR fields into wrap-friendly blocks."""

    if "OCR规则:" not in message:
        return rich_text.text(message)
    chunks = [chunk.strip() for chunk in message.split(" / ") if chunk.strip()]
    normal: list[str] = []
    fields: list[tuple[str, str]] = []
    for chunk in chunks:
        matched = False
        for label in ("OCR规则:", "OCR实际:", "匹配:", "尝试:"):
            if chunk.startswith(label):
                fields.append((label, chunk[len(label):].strip()))
                matched = True
                break
        if not matched:
            normal.append(chunk)
    field_html = "".join(_ocr_field_html(label, value) for label, value in fields)
    tail = ""
    if normal:
        tail = (
            f"<div style=\"margin:0;overflow-wrap:anywhere;word-break:break-all;\">"
            f"{rich_text.text(' / '.join(normal))}</div>"
        )
    return tail + field_html


def _ocr_field_html(label: str, value: str) -> str:
    """Render one highlighted OCR field."""

    color = {
        "OCR规则:": theme.PRIMARY,
        "OCR实际:": theme.DANGER,
        "匹配:": theme.WARNING,
        "尝试:": theme.TEXT_MUTED,
    }[label]
    return (
        f"<div style=\"line-height:1.25;margin:0;overflow-wrap:anywhere;"
        f"word-break:break-all;\">"
        f"<span style=\"display:inline-block;border:1px solid {color};"
        f"color:{color};border-radius:5px;padding:0 4px;font-weight:700;\">"
        f"{rich_text.text(label)}</span> "
        f"<span style=\"color:{theme.TEXT};font-weight:600;\">{rich_text.text(value)}</span>"
        "</div>"
    )
