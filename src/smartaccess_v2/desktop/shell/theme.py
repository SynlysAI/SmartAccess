"""浅色客户端主题。"""

from __future__ import annotations

CANVAS = "#f5f7fb"
SURFACE = "#ffffff"
SURFACE_ALT = "#f8fafc"
BORDER = "#dbe2ee"
BORDER_STRONG = "#c8d2e2"
TEXT = "#172033"
TEXT_MUTED = "#526179"
TEXT_SUBTLE = "#728198"
PRIMARY = "#1f6fd6"
PRIMARY_HOVER = "#165bbf"
PRIMARY_SOFT = "#e9f2ff"
SUCCESS = "#0f9f6e"
WARNING = "#c77900"
DANGER = "#c53030"


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
QLabel#AppTitle {{
    font-size: 18px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#PageTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#PageHint {{
    color: {TEXT_MUTED};
}}
QListWidget#NavList {{
    background: {SURFACE};
    border: none;
    border-right: 1px solid {BORDER};
    padding: 8px;
    outline: 0;
}}
QListWidget#NavList::item {{
    padding: 10px 12px;
    margin: 2px 4px;
    border-radius: 8px;
    color: {TEXT_MUTED};
}}
QListWidget#NavList::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_HOVER};
    border: 1px solid #bcd6ff;
    font-weight: 700;
}}
QPushButton {{
    background: {PRIMARY};
    color: #ffffff;
    border: 1px solid {PRIMARY};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {PRIMARY_HOVER};
}}
QPushButton#Secondary {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
}}
QPushButton#Secondary:hover {{
    border-color: {PRIMARY};
    color: {PRIMARY_HOVER};
}}
QPushButton#Danger {{
    background: #fff7f7;
    color: {DANGER};
    border: 1px solid #efb3b3;
}}
QPushButton#TableAction {{
    background: {SURFACE};
    color: {PRIMARY_HOVER};
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 0px 4px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#TableAction:hover {{
    border-color: {PRIMARY};
    background: {PRIMARY_SOFT};
}}
QPushButton#TableDanger {{
    background: #fff7f7;
    color: {DANGER};
    border: 1px solid #efb3b3;
    border-radius: 5px;
    padding: 0px 4px;
    font-size: 12px;
    font-weight: 600;
}}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTextBrowser,
QTableWidget, QTreeWidget, QListWidget {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 10px;
    font-weight: 700;
}}
QStatusBar {{
    background: {SURFACE};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
}}
QDockWidget::title {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    padding: 8px 10px;
    border-bottom: 1px solid {BORDER};
}}
"""


def apply_theme(app: object) -> None:
    """应用浅色主题。

    Args:
        app: QApplication 实例。
    """

    app.setStyleSheet(build_qss())
