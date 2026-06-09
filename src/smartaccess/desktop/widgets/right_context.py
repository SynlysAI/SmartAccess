"""The right-hand toolbar inspector.

The four facets — 工具详情 / AI 助手 / 风险提示 / 审计摘要 — are stacked
vertically as collapsible sections so several can be read at once, and any one
can be folded away. Bodies render rich HTML for legible, high-contrast key/value
text.
"""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from smartaccess.desktop.shell import theme as t

from .cards import CollapsibleSection, render_lines_html, rich_text


class _Section(CollapsibleSection):
    """A collapsible section whose body is a single rich-text label."""

    def __init__(self, title: str, *, accent: str, expanded: bool = True) -> None:
        super().__init__(title, accent=accent, expanded=expanded)
        self._body = rich_text(QLabel("—"))
        self._body.setStyleSheet("color:%s;" % t.INK_MUTED)
        self.add(self._body)

    def set_lines(self, lines: Iterable[str]) -> None:
        self._body.setText(render_lines_html(list(lines)))

    def set_text(self, text: str) -> None:
        self._body.setText(render_lines_html([text]))


class RightContextPanel(QFrame):
    """Live context inspector shared by every page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RightPanel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.details = _Section("工具详情", accent=t.PRIMARY)
        self.assistant = _Section("AI 助手", accent="#a5b4fc")
        self.risk = _Section("风险提示", accent=t.WARNING)
        self.audit = _Section("审计摘要", accent=t.SUCCESS, expanded=False)
        for section in (self.details, self.assistant, self.risk, self.audit):
            layout.addWidget(section)
        layout.addStretch(1)

        scroll.setWidget(host)
        outer.addWidget(scroll)

    def show_context(
        self,
        *,
        details: Iterable[str] | str = "",
        assistant: Iterable[str] | str = "",
        risk: Iterable[str] | str = "",
        audit: Iterable[str] | str = "",
    ) -> None:
        self.details.set_lines(_as_lines(details))
        self.assistant.set_lines(_as_lines(assistant))
        self.risk.set_lines(_as_lines(risk))
        self.audit.set_lines(_as_lines(audit))


def _as_lines(value: Iterable[str] | str) -> list[str]:
    if isinstance(value, str):
        return [ln for ln in value.split("\n") if ln.strip()]
    return list(value)
