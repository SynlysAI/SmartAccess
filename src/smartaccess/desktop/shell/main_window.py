"""Main window: dockable workbench shell.

Layout is a :class:`QMainWindow` so the left navigation and the right context
inspector are real :class:`QDockWidget` panels — each can be floated, dragged,
hidden, or pinned back. The center holds the page stack. Hiding the right dock
lets a page (e.g. the calibration ROI canvas) reclaim the full width.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.pages.calibration_page import CalibrationPage
from smartaccess.desktop.pages.dashboard_page import DashboardPage
from smartaccess.desktop.pages.monitoring_page import MonitoringPage
from smartaccess.desktop.pages.template_page import TemplatePage
from smartaccess.desktop.pages.workflow_page import WorkflowPage
from smartaccess.desktop.viewmodels.base import EventRelay
from smartaccess.desktop.widgets.right_context import RightContextPanel

_NAV = [
    ("⌂", "工作台首页", "实验执行总览"),
    ("⊞", "设备接入与校准", "窗口识别与 ROI 标注"),
    ("✦", "工作流设计", "AI 生成与标准化"),
    ("❏", "模板库", "版本与发布治理"),
    ("◎", "运行监控", "执行、观测与恢复"),
]


class MainWindow(QMainWindow):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SmartAccess 工作台")
        self.resize(1480, 920)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
        )
        self._facade = facade
        self._relay = EventRelay(facade, self)

        # --- center: top bar + page stack -------------------------------- #
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self._build_top_bar())

        self._stack = QStackedWidget()
        self._pages = [
            DashboardPage(facade),
            CalibrationPage(facade),
            WorkflowPage(facade),
            TemplatePage(facade),
            MonitoringPage(facade, self._relay),
        ]
        for page in self._pages:
            self._stack.addWidget(page)
        center_layout.addWidget(self._stack, 1)
        self.setCentralWidget(center)

        # --- left nav dock ----------------------------------------------- #
        self._nav = QListWidget()
        self._nav.setObjectName("NavList")
        for icon, title, subtitle in _NAV:
            item = QListWidgetItem(f"  {icon}   {title}")
            item.setToolTip(subtitle)
            self._nav.addItem(item)
        self._nav.currentRowChanged.connect(self._on_nav_changed)

        self._nav_dock = self._make_dock("导航", self._nav, width=232)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._nav_dock)

        # --- right context dock ------------------------------------------ #
        self._right = RightContextPanel()
        self._right_dock = self._make_dock("上下文", self._right, width=336)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._right_dock)

        self._wire_view_toggles()
        self._nav.setCurrentRow(0)
        self._refresh_context(0)

    # ------------------------------------------------------------------ #
    def _make_dock(self, title: str, widget: QWidget, *, width: int) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"Dock_{title}")
        dock.setWidget(widget)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        widget.setMinimumWidth(width)
        return dock

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(10)

        # Panel-pin toggles let the user collapse/restore the side docks so the
        # center (e.g. the ROI canvas) can take the full width.
        self._btn_left = self._panel_button("◧", "显示/隐藏 左侧导航栏")
        self._btn_right = self._panel_button("◨", "显示/隐藏 右侧上下文栏")
        layout.addWidget(self._btn_left)
        layout.addWidget(self._btn_right)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background:#272c36;")
        layout.addWidget(sep)

        self._title = QLabel("工作台首页")
        self._title.setObjectName("TopBarTitle")
        layout.addWidget(self._title)
        layout.addStretch(1)
        workspace = QLabel("workspace · 本地内网")
        workspace.setObjectName("TopBarMeta")
        layout.addWidget(workspace)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _panel_button(self, glyph: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(glyph)
        btn.setToolTip(tip)
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QToolButton{background:#1a1e27;color:#c2cad8;border:1px solid #39414f;"
            "border-radius:7px;padding:5px 9px;font-size:14px;}"
            "QToolButton:checked{background:#16315c;color:#f3f6fc;border-color:#3b82f6;}"
            "QToolButton:hover{border-color:#3b82f6;}"
        )
        return btn

    def _wire_view_toggles(self) -> None:
        self._btn_left.toggled.connect(self._nav_dock.setVisible)
        self._btn_right.toggled.connect(self._right_dock.setVisible)
        self._nav_dock.visibilityChanged.connect(
            lambda v: self._btn_left.setChecked(v)
        )
        self._right_dock.visibilityChanged.connect(
            lambda v: self._btn_right.setChecked(v)
        )

    def _on_nav_changed(self, row: int) -> None:
        if row < 0:
            return
        self._stack.setCurrentIndex(row)
        self._title.setText(_NAV[row][1])
        page = self._pages[row]
        # Pages may refresh themselves when shown so newly persisted config
        # (e.g. a generated workflow YAML) is always visible.
        reload_fn = getattr(page, "on_show", None)
        if callable(reload_fn):
            reload_fn()
        self._refresh_context(row)

    def _refresh_context(self, row: int) -> None:
        projection = self._facade.dashboard()
        devices = self._facade.list_instruments()
        workflows = self._facade.list_workflows()
        templates = self._facade.list_templates()
        details = [f"当前页面: {_NAV[row][1]}"]
        if devices:
            details.append(f"设备: {devices[-1].device_id}（锚点 {len(devices[-1].anchors)}）")
        if workflows:
            details.append(f"工作流: {workflows[-1].metadata.workflow_id}")
        if templates:
            details.append(f"模板: {templates[-1].identity}")
        risk_items = []
        if projection.incidents:
            risk_items.extend(f"! {i.type}: {i.detail}" for i in projection.incidents[:3])
        if projection.outbox_failed:
            risk_items.append(f"! 平台补传失败 {projection.outbox_failed} 条")
        if not devices and row in {0, 1, 4}:
            risk_items.append("! 尚未保存可执行仪器画像")
        if not risk_items:
            risk_items.append("+ 当前上下文无阻塞风险")
        audit = [
            f"本地模板: {projection.local_template_count} 个",
            (f"云端模板: {projection.cloud_template_count} 个"
             if projection.cloud_templates_available else "云端模板: 未连接"),
            f"运行记录: {len(projection.recent_runs)} 条",
            f"待处理异常: {len(projection.incidents)} 条",
        ]
        assistant = "DeepSeek 可通过 DEEPSEEK_API_KEY 与 SMARTACCESS_WORKFLOW_GENERATOR=deepseek 启用。"
        if row == 2:
            assistant = "生成工作流时会带入已校准锚点、动作绑定、安全字段和当前设备上下文。"
        elif row == 1:
            assistant = "校准后会保存 ROI 坐标与归一化坐标，供运行时定位和 OCR 使用。"
        self._right.show_context(
            details=details,
            assistant=assistant,
            risk=risk_items,
            audit=audit,
        )
