"""运行监控页面。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from smartaccess_v2.desktop.viewmodels.monitoring_vm import MonitoringViewModel
from smartaccess_v2.desktop.widgets.log_view import LogView
from smartaccess_v2.desktop.widgets.timeline import TimelineTable
from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.shared.events.bus import RuntimeEvent


class MonitoringPage(QWidget):
    """工作流运行和审计监控页面。"""

    def __init__(self, facade: RuntimeFacade, parent: QWidget | None = None) -> None:
        """初始化运行监控页面。

        Args:
            facade: 运行时门面。
            parent: Qt 父对象。
        """

        super().__init__(parent)
        self._vm = MonitoringViewModel(facade, self)
        self._vm.changed.connect(self._refresh)
        self._vm.event_received.connect(self._on_event)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([300, 520, 520])
        root.addWidget(splitter, 1)

        self._reload_workflows()
        self._refresh()

    def closeEvent(self, event) -> None:  # noqa: N802
        """页面关闭时释放订阅。"""

        self._vm.close()
        super().closeEvent(event)

    def on_show(self) -> None:
        """页面显示时刷新工作流和会话。"""

        self._reload_workflows()
        self._refresh()

    def _build_header(self) -> QHBoxLayout:
        """构建顶部操作区。"""

        row = QHBoxLayout()
        title = QLabel("运行监控")
        title.setObjectName("PageTitle")
        row.addWidget(title)
        row.addStretch(1)
        self._workflow_combo = QComboBox()
        self._workflow_combo.setMinimumWidth(260)
        row.addWidget(self._workflow_combo)
        start_btn = QPushButton("开始")
        start_btn.clicked.connect(self._start)
        row.addWidget(start_btn)
        stop_btn = QPushButton("停止")
        stop_btn.setObjectName("Danger")
        stop_btn.clicked.connect(self._stop)
        row.addWidget(stop_btn)
        return row

    def _build_left_panel(self) -> QWidget:
        """构建会话列表面板。"""

        panel = QWidget()
        panel.setMinimumWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(8)
        label = QLabel("运行会话")
        label.setObjectName("PageHint")
        layout.addWidget(label)
        self._session_list = QListWidget()
        self._session_list.itemSelectionChanged.connect(self._select_session)
        layout.addWidget(self._session_list, 1)
        return panel

    def _build_center_panel(self) -> QWidget:
        """构建步骤时间线面板。"""

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(8)
        self._status = QLabel("状态: 未运行")
        self._status.setObjectName("PageHint")
        layout.addWidget(self._status)
        self._timeline = TimelineTable()
        layout.addWidget(self._timeline, 1)
        self._audit = QTextEdit()
        self._audit.setReadOnly(True)
        self._audit.setMaximumHeight(150)
        layout.addWidget(self._audit)
        return panel

    def _build_right_panel(self) -> QWidget:
        """构建日志面板。"""

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel("运行日志")
        label.setObjectName("PageHint")
        layout.addWidget(label)
        self._log = LogView()
        layout.addWidget(self._log, 1)
        return panel

    def _reload_workflows(self) -> None:
        """刷新工作流下拉框。"""

        current = self._workflow_combo.currentData()
        self._workflow_combo.blockSignals(True)
        self._workflow_combo.clear()
        for workflow in self._vm.list_workflows():
            workflow_id = workflow.metadata.workflow_id
            self._workflow_combo.addItem(workflow_id, workflow_id)
        index = self._workflow_combo.findData(current)
        if index >= 0:
            self._workflow_combo.setCurrentIndex(index)
        self._workflow_combo.blockSignals(False)

    def _refresh(self) -> None:
        """刷新页面显示。"""

        active = self._vm.active_session()
        self._refresh_sessions(active.session_id if active else None)
        self._timeline.set_session(active)
        if active is None:
            self._status.setText("状态: 未运行")
            self._audit.clear()
        else:
            self._status.setText(
                f"状态: {active.status.value} / 会话: {active.session_id}"
            )
            self._audit.setPlainText(self._audit_text(active.session_id))
        self._log.set_entries(self._vm.logs())

    def _refresh_sessions(self, active_id: str | None) -> None:
        """刷新运行会话列表。"""

        self._session_list.blockSignals(True)
        self._session_list.clear()
        sessions = self._vm.list_sessions()
        for session in sessions:
            text = f"{session.session_id} / {session.workflow_id} / {session.status.value}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, session.session_id)
            self._session_list.addItem(item)
            if session.session_id == active_id:
                self._session_list.setCurrentItem(item)
        if not sessions:
            self._session_list.addItem("暂无运行记录")
        self._session_list.blockSignals(False)

    def _select_session(self) -> None:
        """选择运行会话。"""

        item = self._session_list.currentItem()
        if item is None:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        self._vm.set_active_session(str(session_id) if session_id else None)

    def _start(self) -> None:
        """启动当前选择的工作流。"""

        workflow_id = self._workflow_combo.currentData()
        if not workflow_id:
            QMessageBox.warning(self, "无法启动", "请先在工作流设计页保存工作流")
            return
        try:
            self._vm.start_run(str(workflow_id))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "启动失败", str(exc))

    def _stop(self) -> None:
        """请求停止当前运行。"""

        if not self._vm.stop_run():
            QMessageBox.information(self, "停止运行", "当前没有可停止的运行")

    def _on_event(self, event: RuntimeEvent) -> None:
        """更新最近观察摘要。"""

        if event.name.value == "run.step.observed":
            self._audit.setPlainText(self._observation_text(event))

    def _audit_text(self, session_id: str) -> str:
        """构建会话审计摘要。"""

        session = self._vm.facade.get_session(session_id)
        if session is None:
            return ""
        trace = self._vm.facade.get_trace(session_id)
        return (
            f"工作流: {session.workflow_id}\n"
            f"状态: {session.status.value}\n"
            f"步骤数: {len(session.steps)}\n"
            f"轨迹记录: {len(trace)}"
        )

    @staticmethod
    def _observation_text(event: RuntimeEvent) -> str:
        """构建观察事件文本。"""

        payload = event.payload
        return (
            f"步骤: {payload.get('step_id')}\n"
            f"期望: {payload.get('expected_text') or '-'}\n"
            f"实际: {payload.get('actual_text') or '-'}\n"
            f"匹配: {payload.get('matched')}\n"
            f"尝试: {payload.get('attempts')}\n"
            f"耗时: {float(payload.get('elapsed_seconds') or 0):.2f}s\n"
            f"截图: {payload.get('screenshot_path') or '-'}"
        )
