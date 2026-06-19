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

        boundary = _boundary_html(entry)
        if boundary:
            return boundary
        color = {
            "ERROR": theme.DANGER,
            "WARN": theme.WARNING,
            "INFO": theme.TEXT,
        }.get(entry.level, theme.TEXT)
        message = _message_html(entry.message)
        return (
            f"<div style=\"margin:0;color:{color};\">"
            f"<div style=\"line-height:1.15;margin:0;\">"
            f"<span style=\"color:{theme.TEXT_MUTED};\">{rich_text.text(entry.timestamp)}</span> "
            f"<span style=\"color:{color};font-weight:700;\">[{rich_text.text(entry.level)}]</span>"
            "</div>"
            f"<div style=\"line-height:1.2;margin:0 0 0 10px;overflow-wrap:anywhere;word-break:break-all;\">"
            f"{message}"
            "</div>"
            "</div>"
        )


def _boundary_html(entry: MonitorLogEntry) -> str:
    """Render run START/END events as visual separators with context."""

    if not (entry.message.startswith("START / ") or entry.message.startswith("END ")):
        return ""
    color = theme.SUCCESS if entry.message.startswith("START / ") else theme.PRIMARY
    if entry.level == "ERROR":
        color = theme.DANGER
    separator = "=" * 30
    parts = [part.strip() for part in entry.message.split(" / ") if part.strip()]
    title = parts[0] if parts else entry.message
    context = parts[1:]
    context_html = "".join(
        f"<div style=\"line-height:1.35;margin:1px 0;overflow-wrap:anywhere;"
        f"word-break:break-all;\">{rich_text.text(item)}</div>"
        for item in context
    )
    return (
        "<br><br>"
        f"<div style=\"background-color:{theme.SURFACE_ALT};border:1px solid {color};"
        f"border-left:4px solid {color};border-radius:6px;padding:7px 10px;"
        f"margin:0 0 8px 0;color:{theme.TEXT};\">"
        f"<div style=\"font-family:Consolas,'Microsoft YaHei',monospace;"
        f"color:{color};font-weight:700;\">{rich_text.text(separator)}</div>"
        f"<div style=\"line-height:1.3;margin:3px 0;font-weight:700;color:{color};\">"
        f"{rich_text.text(title)} · 运行上下文 · {rich_text.text(entry.timestamp)} "
        f"[{rich_text.text(entry.level)}]</div>"
        f"{context_html}"
        f"<div style=\"font-family:Consolas,'Microsoft YaHei',monospace;"
        f"color:{color};font-weight:700;margin-top:3px;\">"
        f"{rich_text.text(separator)}</div>"
        "</div>"
        "<br>"
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
