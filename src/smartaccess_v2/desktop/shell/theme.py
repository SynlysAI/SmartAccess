"""浅色客户端主题。"""

from __future__ import annotations

CANVAS = "#F5F7FA"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#FAFBFC"
SURFACE_MUTED = "#F0F3F8"
BORDER = "#E2E8F0"
BORDER_LIGHT = "#EBEBEF"
BORDER_STRONG = "#CBD5E1"
TEXT = "#111827"
TEXT_MUTED = "#4B5B73"
TEXT_SUBTLE = "#7A8798"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_PRESSED = "#1E40AF"
PRIMARY_SOFT = "#E8F1FF"
SUCCESS = "#0F9F6E"
WARNING = "#C77900"
DANGER = "#DC2626"
DANGER_SOFT = "#FFF1F2"
SHADOW = "rgba(15, 23, 42, 0.06)"


def build_qss() -> str:
    """构建 Qt 样式表。

    Returns:
        Qt QSS 样式表。
    """

    return f"""
QWidget {{
    background-color: {CANVAS};
    color: {TEXT};
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}}
QMainWindow, QMainWindow > QWidget {{
    background-color: {CANVAS};
}}
QFrame#TopBar {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QFrame#Card, QFrame#RightPanel {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#SectionCard {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel#AppTitle {{
    font-size: 18px;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}
QLabel#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT};
    background: transparent;
}}
QLabel#PageHint, QLabel#SectionTitle {{
    color: {TEXT_MUTED};
    background: transparent;
}}
QListWidget#NavList {{
    background: {SURFACE};
    border: none;
    border-right: 1px solid {BORDER};
    padding: 12px 10px;
    outline: 0;
}}
QListWidget#NavList::item {{
    min-height: 42px;
    padding: 10px 12px 10px 36px;
    margin: 4px 0px;
    border-radius: 8px;
    color: {TEXT_MUTED};
    border-left: 3px solid transparent;
}}
QListWidget#NavList::item:hover {{
    background: {SURFACE_ALT};
    color: {TEXT};
}}
QListWidget#NavList::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_HOVER};
    border-left: 3px solid {PRIMARY};
    font-weight: 700;
}}
QPushButton {{
    background: {PRIMARY};
    color: #ffffff;
    border: 1px solid {PRIMARY};
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 22px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {PRIMARY_HOVER};
    border-color: {PRIMARY_HOVER};
}}
QPushButton:pressed {{
    background: {PRIMARY_PRESSED};
    border-color: {PRIMARY_PRESSED};
}}
QPushButton:disabled {{
    background: {SURFACE_MUTED};
    color: {TEXT_SUBTLE};
    border-color: {BORDER};
}}
QPushButton#Secondary {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
}}
QPushButton#Secondary:hover {{
    background: {SURFACE_ALT};
    border-color: {PRIMARY};
    color: {PRIMARY_HOVER};
}}
QPushButton#Danger {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #FDA4AF;
}}
QPushButton#Danger:hover {{
    background: #FFE4E6;
    border-color: {DANGER};
}}
QPushButton#TableAction {{
    background: {SURFACE};
    color: {PRIMARY_HOVER};
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 0px 6px;
    min-height: 24px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#TableAction:hover {{
    border-color: {PRIMARY};
    background: {PRIMARY_SOFT};
}}
QPushButton#TableDanger {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #FDA4AF;
    border-radius: 5px;
    padding: 0px 6px;
    min-height: 24px;
    font-size: 12px;
    font-weight: 600;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QTextBrowser {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {PRIMARY};
}}
QComboBox::drop-down {{
    width: 24px;
    border: none;
}}
QCheckBox {{
    background: transparent;
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER_STRONG};
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}
QListWidget {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: 0;
}}
QListWidget::item {{
    min-height: 30px;
    padding: 6px 10px;
    border-radius: 5px;
}}
QListWidget::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_HOVER};
}}
QTableWidget {{
    background: {SURFACE};
    alternate-background-color: #FBFCFE;
    color: {TEXT};
    border: none;
    border-radius: 0px;
    gridline-color: {BORDER_LIGHT};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
}}
QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {BORDER_LIGHT};
}}
QTableWidget::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER_LIGHT};
    padding: 9px 10px;
    font-weight: 700;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 8px;
}}
QStatusBar {{
    background: {SURFACE};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
}}
QGraphicsView#RoiCanvas {{
    background: {SURFACE_MUTED};
    border: none;
    border-radius: 8px;
}}
"""


def apply_theme(app: object) -> None:
    """应用浅色主题。

    Args:
        app: QApplication 实例。
    """

    app.setStyleSheet(build_qss())
