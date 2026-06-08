"""Neutral light theme for the SmartAccess workbench.

The `xyzen.ai` reference informs information architecture only, not brand color
or dark styling (PRD §8.9). This QSS is a calm, neutral light theme.
"""

from __future__ import annotations

# Palette
BG = "#f5f6f8"
SURFACE = "#ffffff"
BORDER = "#e2e5ea"
TEXT = "#1f2430"
MUTED = "#6b7280"
PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"

LIGHT_QSS = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}}
#NavList {{
    background-color: {SURFACE};
    border: none;
    border-right: 1px solid {BORDER};
    padding: 8px;
    outline: 0;
}}
#NavList::item {{
    padding: 10px 14px;
    border-radius: 8px;
    margin: 2px 4px;
    color: {MUTED};
}}
#NavList::item:selected {{
    background-color: {PRIMARY};
    color: white;
}}
#NavList::item:hover:!selected {{
    background-color: {BG};
    color: {TEXT};
}}
#TopBar {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
#TopBarTitle {{ font-size: 16px; font-weight: 600; }}
#RightPanel {{
    background-color: {SURFACE};
    border-left: 1px solid {BORDER};
}}
QFrame#Card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#CardTitle {{ font-size: 13px; color: {MUTED}; }}
QLabel#StatValue {{ font-size: 26px; font-weight: 700; color: {TEXT}; }}
QLabel#PageTitle {{ font-size: 20px; font-weight: 700; }}
QLabel#PageSubtitle {{ color: {MUTED}; }}
QLabel#SectionTitle {{ font-size: 14px; font-weight: 600; }}
QPushButton {{
    background-color: {PRIMARY};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {PRIMARY_HOVER}; }}
QPushButton:disabled {{ background-color: #c7cdd6; color: #eef0f3; }}
QPushButton#Ghost {{
    background-color: transparent;
    color: {PRIMARY};
    border: 1px solid {BORDER};
}}
QPushButton#Ghost:hover {{ background-color: {BG}; }}
QListWidget, QTreeWidget, QTableWidget, QTextEdit, QPlainTextEdit, QLineEdit, QComboBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}
QPlainTextEdit#LogView {{
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}}
"""


def apply_theme(app: object) -> None:
    """Apply the light QSS to a ``QApplication`` instance."""

    app.setStyleSheet(LIGHT_QSS)
