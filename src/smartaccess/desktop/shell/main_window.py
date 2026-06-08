"""Main window: unified layout (top bar + left nav + center pages + right panel)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
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
    ("工作台首页", "实验执行总览"),
    ("设备接入与校准", "窗口识别与 ROI 标注"),
    ("工作流设计", "AI 生成与标准化"),
    ("模板库", "版本与发布治理"),
    ("运行监控", "执行、观测与恢复"),
]


class MainWindow(QMainWindow):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SmartAccess 工作台")
        self.resize(1400, 880)
        self._facade = facade
        self._relay = EventRelay(facade, self)

        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._nav = QTreeWidget()
        self._nav.setObjectName("NavList")
        self._nav.setFixedWidth(230)
        self._nav.setHeaderHidden(True)
        for title, subtitle in _NAV:
            item = QTreeWidgetItem([title])
            item.setToolTip(0, subtitle)
            self._nav.addTopLevelItem(item)
        self._nav.currentItemChanged.connect(self._on_nav_changed)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self._build_top_bar())

        self._stack = QStackedWidget()
        self._stack.addWidget(DashboardPage(facade))
        self._stack.addWidget(CalibrationPage(facade))
        self._stack.addWidget(WorkflowPage(facade))
        self._stack.addWidget(TemplatePage(facade))
        self._stack.addWidget(MonitoringPage(facade, self._relay))
        center_layout.addWidget(self._stack, 1)

        self._right = RightContextPanel()

        outer.addWidget(self._nav)
        outer.addWidget(center, 1)
        outer.addWidget(self._right)
        self.setCentralWidget(central)

        self._nav.setCurrentItem(self._nav.topLevelItem(0))
        self._refresh_context(0)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        self._title = QLabel("工作台首页")
        self._title.setObjectName("TopBarTitle")
        workspace = QLabel("workspace · 本地内网")
        workspace.setStyleSheet("color:#6b7280;")
        layout.addWidget(self._title)
        layout.addStretch(1)
        layout.addWidget(workspace)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _on_nav_changed(self, current, _previous) -> None:
        if current is None:
            return
        row = self._nav.indexOfTopLevelItem(current)
        if row < 0:
            return
        self._stack.setCurrentIndex(row)
        self._title.setText(_NAV[row][0])
        self._refresh_context(row)

    def _refresh_context(self, row: int) -> None:
        projection = self._facade.dashboard()
        devices = self._facade.list_instruments()
        workflows = self._facade.list_workflows()
        templates = self._facade.list_templates()
        details = [f"当前页面：{_NAV[row][0]}"]
        if devices:
            details.append(f"设备：{devices[-1].device_id}（锚点 {len(devices[-1].anchors)}）")
        if workflows:
            details.append(f"工作流：{workflows[-1].metadata.workflow_id}")
        if templates:
            details.append(f"模板：{templates[-1].identity}")
        risk_items = []
        if projection.incidents:
            risk_items.extend(f"{i.type}: {i.detail}" for i in projection.incidents[:3])
        if projection.outbox_failed:
            risk_items.append(f"平台补传失败 {projection.outbox_failed} 条")
        if not devices and row in {0, 1, 4}:
            risk_items.append("尚未保存可执行仪器画像")
        if not risk_items:
            risk_items.append("当前上下文无阻塞风险")
        audit = [
            f"本地模板 {projection.local_template_count} 个",
            f"云端模板 {projection.cloud_template_count} 个" if projection.cloud_templates_available else "云端模板未连接",
            f"运行记录 {len(projection.recent_runs)} 条",
            f"待处理异常 {len(projection.incidents)} 条",
        ]
        assistant = "DeepSeek 可通过 DEEPSEEK_API_KEY 与 SMARTACCESS_WORKFLOW_GENERATOR=deepseek 启用。"
        if row == 2:
            assistant = "生成工作流时会带入已校准锚点、动作绑定、安全字段和当前设备上下文。"
        elif row == 1:
            assistant = "校准后会保存 ROI 坐标与归一化坐标，供运行时定位和 OCR 使用。"
        self._right.show_context(
            details="\n".join(details),
            assistant=assistant,
            risk="\n".join(risk_items),
            audit="\n".join(audit),
        )
