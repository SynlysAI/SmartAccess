"""Qt stylesheet builder for the SmartAccess dark theme.

Kept separate from :mod:`theme` so the palette constants stay easy to scan and
the (long) QSS string lives in one place.
"""

from __future__ import annotations


def build_qss() -> str:
    from smartaccess.desktop.shell import theme as t

    return _BASE.format(
        CANVAS=t.CANVAS,
        SURFACE_1=t.SURFACE_1,
        SURFACE_2=t.SURFACE_2,
        SURFACE_3=t.SURFACE_3,
        SURFACE_4=t.SURFACE_4,
        HAIRLINE=t.HAIRLINE,
        HAIRLINE_STRONG=t.HAIRLINE_STRONG,
        INK=t.INK,
        INK_MUTED=t.INK_MUTED,
        INK_SUBTLE=t.INK_SUBTLE,
        INK_FAINT=t.INK_FAINT,
        PRIMARY=t.PRIMARY,
        PRIMARY_HOVER=t.PRIMARY_HOVER,
        PRIMARY_PRESSED=t.PRIMARY_PRESSED,
        PRIMARY_SOFT=t.PRIMARY_SOFT,
        SUCCESS=t.SUCCESS,
        DANGER=t.DANGER,
    )


_BASE = """
/* ---- Global ---------------------------------------------------------- */
QWidget {{
    background-color: {CANVAS};
    color: {INK};
    font-family: "Segoe UI", "Microsoft YaHei", "Inter", sans-serif;
    font-size: 13px;
}}
QToolTip {{
    background-color: {SURFACE_3};
    color: {INK};
    border: 1px solid {HAIRLINE_STRONG};
    border-radius: 6px;
    padding: 6px 9px;
}}

/* ---- Main window / docks --------------------------------------------- */
QMainWindow, QMainWindow > QWidget {{ background-color: {CANVAS}; }}
QMainWindow::separator {{
    background-color: {HAIRLINE};
    width: 1px;
    height: 1px;
}}
QMainWindow::separator:hover {{ background-color: {PRIMARY}; }}

QDockWidget {{
    color: {INK_SUBTLE};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: {SURFACE_1};
    color: {INK_MUTED};
    padding: 8px 12px;
    border-bottom: 1px solid {HAIRLINE};
    font-weight: 600;
    text-align: left;
}}
QDockWidget > QWidget {{ background-color: {SURFACE_1}; }}
QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
    padding: 2px;
}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background-color: {SURFACE_3};
    border-radius: 4px;
}}

/* ---- Left navigation ------------------------------------------------- */
#NavList {{
    background-color: {SURFACE_1};
    border: none;
    border-right: 1px solid {HAIRLINE};
    padding: 8px;
    outline: 0;
}}
#NavList::item {{
    padding: 9px 12px;
    border-radius: 8px;
    margin: 2px 4px;
    color: {INK_SUBTLE};
}}
#NavList::item:selected {{
    background-color: {PRIMARY_SOFT};
    color: {INK};
    border: 1px solid {PRIMARY};
}}
#NavList::item:hover:!selected {{
    background-color: {SURFACE_2};
    color: {INK};
}}

/* ---- Top bar --------------------------------------------------------- */
#TopBar {{
    background-color: {SURFACE_1};
    border-bottom: 1px solid {HAIRLINE};
}}
#TopBarTitle {{ font-size: 17px; font-weight: 700; color: {INK}; }}
#TopBarMeta {{ color: {INK_SUBTLE}; font-size: 12px; }}

#RightPanel {{
    background-color: {SURFACE_1};
    border-left: 1px solid {HAIRLINE};
}}

/* ---- Cards & surfaces ------------------------------------------------ */
QFrame#Card {{
    background-color: {SURFACE_1};
    border: 1px solid {HAIRLINE};
    border-radius: 12px;
}}
QFrame#CardFlush {{
    background-color: {SURFACE_1};
    border: none;
    border-radius: 0px;
}}
QFrame#Divider {{
    background-color: {HAIRLINE};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* ---- Typography roles ------------------------------------------------ */
QLabel#PageTitle {{ font-size: 21px; font-weight: 700; color: {INK}; }}
QLabel#PageSubtitle {{ color: {INK_SUBTLE}; font-size: 13px; }}
QLabel#SectionTitle {{ font-size: 13px; font-weight: 700; color: {INK}; }}
QLabel#CardTitle {{ font-size: 12px; color: {INK_SUBTLE}; font-weight: 600; }}
QLabel#StatValue {{ font-size: 28px; font-weight: 700; color: {INK}; }}
QLabel#Eyebrow {{ font-size: 11px; font-weight: 700; color: {INK_SUBTLE}; }}
QLabel#Body {{ color: {INK_MUTED}; }}
QLabel#Hint {{ color: {INK_SUBTLE}; font-size: 12px; }}

/* ---- Buttons --------------------------------------------------------- */
QPushButton {{
    background-color: {PRIMARY};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: {PRIMARY_HOVER}; }}
QPushButton:pressed {{ background-color: {PRIMARY_PRESSED}; }}
QPushButton:disabled {{ background-color: {SURFACE_3}; color: {INK_FAINT}; }}

QPushButton#Ghost {{
    background-color: {SURFACE_2};
    color: {INK};
    border: 1px solid {HAIRLINE_STRONG};
}}
QPushButton#Ghost:hover {{ background-color: {SURFACE_3}; border-color: {PRIMARY}; }}
QPushButton#Ghost:pressed {{ background-color: {SURFACE_4}; }}
QPushButton#Ghost:disabled {{ color: {INK_FAINT}; border-color: {HAIRLINE}; }}

QPushButton#Danger {{
    background-color: transparent;
    color: {DANGER};
    border: 1px solid {HAIRLINE_STRONG};
}}
QPushButton#Danger:hover {{ background-color: #2a1417; border-color: {DANGER}; }}

QPushButton#SectionToggle {{
    background-color: transparent;
    color: {INK};
    border: none;
    border-radius: 6px;
    padding: 8px 10px;
    font-weight: 700;
    text-align: left;
}}
QPushButton#SectionToggle:hover {{ background-color: {SURFACE_2}; }}

/* ---- Inputs ---------------------------------------------------------- */
QListWidget, QTreeWidget, QTableWidget, QTextEdit, QPlainTextEdit,
QLineEdit, QComboBox, QSpinBox, QTextBrowser {{
    background-color: {SURFACE_2};
    color: {INK};
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
    padding: 6px;
    selection-background-color: {PRIMARY};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus,
QListWidget:focus, QTreeWidget:focus, QTableWidget:focus {{
    border: 1px solid {PRIMARY};
}}
QLineEdit::placeholder {{ color: {INK_FAINT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_3};
    color: {INK};
    border: 1px solid {HAIRLINE_STRONG};
    selection-background-color: {PRIMARY};
    selection-color: #ffffff;
    outline: 0;
}}

/* ---- Lists / trees / tables ----------------------------------------- */
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; color: {INK_MUTED}; }}
QListWidget::item:selected {{ background-color: {PRIMARY_SOFT}; color: {INK}; }}
QListWidget::item:hover:!selected {{ background-color: {SURFACE_3}; }}

QHeaderView::section {{
    background-color: {SURFACE_3};
    color: {INK_MUTED};
    border: none;
    border-bottom: 1px solid {HAIRLINE_STRONG};
    padding: 8px 10px;
    font-weight: 600;
    font-size: 14px;
}}
QTableWidget {{ gridline-color: {HAIRLINE}; font-size: 15px; }}
QTableWidget::item {{ padding: 8px 10px; color: {INK_MUTED}; }}
QTableWidget::item:selected {{ background-color: {PRIMARY_SOFT}; color: {INK}; }}
QTreeWidget::item {{ padding: 5px 4px; color: {INK_MUTED}; }}
QTreeWidget::item:selected {{ background-color: {PRIMARY_SOFT}; color: {INK}; }}

/* ---- Tabs (used where stacking is not appropriate) ------------------ */
QTabWidget::pane {{ border: 1px solid {HAIRLINE}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background-color: transparent;
    color: {INK_SUBTLE};
    padding: 7px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 4px;
}}
QTabBar::tab:selected {{ color: {INK}; border-bottom: 2px solid {PRIMARY}; }}
QTabBar::tab:hover:!selected {{ color: {INK_MUTED}; }}

/* ---- Log / mono ------------------------------------------------------ */
QPlainTextEdit#LogView, QTextBrowser#LogView {{
    background-color: {CANVAS};
    font-family: "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
    font-size: 12px;
    color: {INK_MUTED};
}}

/* ---- Scrollbars ------------------------------------------------------ */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_4}; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {HAIRLINE_STRONG}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_4}; border-radius: 5px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QCheckBox {{ color: {INK_MUTED}; spacing: 7px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {HAIRLINE_STRONG}; background: {SURFACE_2};
}}
QCheckBox::indicator:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; }}
QScrollArea {{ border: none; background: transparent; }}
"""
