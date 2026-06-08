"""Small reusable widgets for the workbench (cards, stat cards, section titles)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class Card(QFrame):
    """A rounded surface container with a vertical layout."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(8)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class StatCard(Card):
    """A card showing a title and a big numeric/text value."""

    def __init__(self, title: str, value: str = "0", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        self.add(self._title)
        self.add(self._value)
        self._layout.addStretch(1)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def page_header(title: str, subtitle: str = "") -> QWidget:
    """A page title + optional subtitle block."""

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
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
