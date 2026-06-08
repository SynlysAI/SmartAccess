"""Small reusable widgets for the workbench: cards, stat cards, section titles,
collapsible sections, dividers, and rich-text rendering helpers."""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.shell import theme as t


class Card(QFrame):
    """A rounded surface container with a vertical layout."""

    def __init__(self, parent: QWidget | None = None, *, flush: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlush" if flush else "Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(10)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class StatCard(Card):
    """A card showing a title, a big value, and an optional trend caption."""

    def __init__(self, title: str, value: str = "0", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout.setSpacing(6)
        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        self._caption = QLabel("")
        self._caption.setObjectName("Hint")
        self._caption.setVisible(False)
        self.add(self._title)
        self.add(self._value)
        self.add(self._caption)
        self._layout.addStretch(1)

    def set_value(self, value: str) -> None:
        self._value.setText(value)

    def set_accent(self, color: str) -> None:
        self._value.setStyleSheet(f"font-size:28px;font-weight:700;color:{color};")

    def set_caption(self, text: str) -> None:
        self._caption.setText(text)
        self._caption.setVisible(bool(text))


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def page_header(title: str, subtitle: str = "") -> QWidget:
    """A page title + optional subtitle block."""

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    layout.addWidget(title_label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    return container


class CollapsibleSection(QFrame):
    """A header row that toggles a content body open/closed.

    Used to vertically stack the context inspector (上下文 / AI / 风险 / 审计)
    instead of a tab control, so several sections can be read at once and any
    one collapsed to save room.
    """

    def __init__(
        self,
        title: str,
        *,
        accent: str | None = None,
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._accent = accent or t.PRIMARY
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)

        header = QWidget()
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(f"color:{self._accent};font-size:11px;")
        self._toggle = QPushButton(title)
        self._toggle.setObjectName("SectionToggle")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self.toggle)
        self._chevron = QLabel("▾")
        self._chevron.setStyleSheet(f"color:{t.INK_SUBTLE};font-size:11px;")
        header_row.addWidget(self._dot)
        header_row.addWidget(self._toggle, 1)
        header_row.addWidget(self._chevron)
        outer.addWidget(header)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 4, 8, 8)
        self._content_layout.setSpacing(6)
        outer.addWidget(self._content)

        self._expanded = expanded
        self._apply_state()

    def add(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._apply_state()

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._apply_state()

    def _apply_state(self) -> None:
        self._content.setVisible(self._expanded)
        self._chevron.setText("▾" if self._expanded else "▸")


def rich_text(label: QLabel) -> QLabel:
    """Configure a label to render rich text with wrapping and link support."""

    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


def render_lines_html(lines: list[str], *, empty: str = "—") -> str:
    """Render ``key: value`` style lines as a compact two-tone HTML block.

    A leading ``! `` marks a line as a warning (rendered in the danger color);
    a leading ``+ `` marks success. The portion before the first colon is
    emphasized as a key, the remainder as muted body — never gray-on-gray.
    """

    rows = [ln for ln in (lines or []) if ln and ln.strip()]
    if not rows:
        return f"<span style='color:{t.INK_SUBTLE};'>{html.escape(empty)}</span>"
    out: list[str] = ["<div style='line-height:170%;'>"]
    for raw in rows:
        line = raw.strip()
        color = t.INK_MUTED
        marker = ""
        if line.startswith("! "):
            color, marker, line = t.DANGER, "⚠ ", line[2:]
        elif line.startswith("+ "):
            color, marker, line = t.SUCCESS, "✓ ", line[2:]
        if ":" in line:
            key, _, value = line.partition(":")
            out.append(
                f"<div>{marker}<span style='color:{t.INK};font-weight:600;'>"
                f"{html.escape(key)}</span>"
                f"<span style='color:{color};'>:{html.escape(value)}</span></div>"
            )
        else:
            out.append(f"<div style='color:{color};'>{marker}{html.escape(line)}</div>")
    out.append("</div>")
    return "".join(out)
