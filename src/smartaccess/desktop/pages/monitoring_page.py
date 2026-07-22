"""运行监控页面。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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

from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel
from smartaccess.desktop.widgets.log_view import LogView
from smartaccess.desktop.widgets import rich_text
from smartaccess.desktop.widgets.table_style import NoWheelComboBox
from smartaccess.desktop.widgets.timeline import TimelineTable
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.shared.events.bus import RuntimeEvent
from smartaccess.shared.events.runtime import RuntimeEventName


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
        root.addWidget(self._build_workflow_info())

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
        row.addWidget(QLabel("工作流:"))
        self._workflow_combo = NoWheelComboBox()
        self._workflow_combo.setMinimumWidth(260)
        self._workflow_combo.currentIndexChanged.connect(self._refresh_workflow_info)
        row.addWidget(self._workflow_combo)
        start_btn = QPushButton("开始")
        start_btn.clicked.connect(self._start)
        row.addWidget(start_btn)
        stop_btn = QPushButton("停止")
        stop_btn.setObjectName("Danger")
        stop_btn.clicked.connect(self._stop)
        row.addWidget(stop_btn)
        return row

    def _build_workflow_info(self) -> QTextEdit:
        """构建工作流绑定设备摘要区。"""

        self._workflow_info = QTextEdit()
        self._workflow_info.setObjectName("WorkflowRunSummary")
        self._workflow_info.setReadOnly(True)
        self._workflow_info.setMinimumHeight(100)
        self._workflow_info.setMaximumHeight(150)
        self._workflow_info.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        return self._workflow_info

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
        header = QHBoxLayout()
        label = QLabel("运行日志")
        label.setObjectName("PageHint")
        header.addWidget(label)
        header.addStretch(1)
        clear_btn = QPushButton("清空日志")
        clear_btn.setObjectName("Secondary")
        clear_btn.clicked.connect(self._clear_logs)
        header.addWidget(clear_btn)
        layout.addLayout(header)
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
        self._refresh_workflow_info()

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
            self._audit.setHtml(self._audit_html(active.session_id))
        self._log.set_entries(self._vm.logs())

    def _refresh_workflow_info(self) -> None:
        """刷新当前工作流绑定设备摘要。"""

        workflow_id = self._workflow_combo.currentData()
        summary = self._vm.workflow_summary(str(workflow_id) if workflow_id else None)
        if summary is None:
            self._workflow_info.setHtml(
                rich_text.panel(
                    "工作流绑定设备",
                    rich_text.paragraph("工作流: -\n绑定设备: -"),
                )
            )
            return
        self._workflow_info.setHtml(self._workflow_info_html(summary))

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

    def _clear_logs(self) -> None:
        """清空运行日志。"""

        self._vm.clear_logs()

    def _on_event(self, event: RuntimeEvent) -> None:
        """更新最近观察摘要。"""

        if event.name.value == "run.step.observed":
            self._audit.setHtml(self._observation_html(event))
        elif event.name == RuntimeEventName.RUN_BLOCKED:
            self._handle_blocked_event(event)

    @staticmethod
    def _confirm_yes_button() -> QMessageBox.StandardButton:
        """Return the QMessageBox yes button; useful for tests."""

        return QMessageBox.StandardButton.Yes

    def _handle_blocked_event(self, event: RuntimeEvent) -> None:
        """Handle runtime blocked events with visible operator prompts."""

        payload = event.payload
        if payload.get("incident_type") == "WindowMissing":
            self._show_window_missing_warning(payload)
            return
        session_id = event.session_id
        step_id = str(payload.get("step_id") or "")
        if not session_id or not step_id:
            return
        reason = str(payload.get("reason") or payload.get("detail") or "该步骤需要人工确认")
        confirmed = self._ask_manual_confirmation(reason)
        self._vm.resolve_confirmation(
            session_id,
            step_id,
            confirmed,
        )

    def _ask_manual_confirmation(self, reason: str) -> bool:
        """激活主窗口并显示置顶的人工确认弹窗。

        Args:
            reason: 当前步骤需要人工确认的原因。

        Returns:
            用户确认继续时返回 True。
        """

        window = self.window()
        if window.isMinimized():
            window.showNormal()
        window.show()
        window.raise_()
        window.activateWindow()

        message_box = QMessageBox(window)
        message_box.setIcon(QMessageBox.Icon.Question)
        message_box.setWindowTitle("人工确认")
        message_box.setText(
            f"{reason}\n\n确认后继续运行，取消后工作流保持阻塞。"
        )
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        message_box.setEscapeButton(QMessageBox.StandardButton.No)
        message_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        message_box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        message_box.show()
        message_box.raise_()
        message_box.activateWindow()
        message_box.exec()
        return (
            message_box.standardButton(message_box.clickedButton())
            == QMessageBox.StandardButton.Yes
        )

    def _show_window_missing_warning(self, payload: dict) -> None:
        """Show a warning when the controlled app window is not found."""

        profile = payload.get("anchor_profile") or "-"
        title = payload.get("title_contains") or "-"
        detail = payload.get("detail") or payload.get("reason") or "未找到目标窗口"
        QMessageBox.warning(
            self,
            "未检测到目标窗口",
            (
                f"{detail}\n\n"
                f"绑定设备: {profile}\n"
                f"窗口标题: {title}\n\n"
                "请打开被控软件或重新扫描窗口后再运行。"
            ),
        )

    def _audit_html(self, session_id: str) -> str:
        """构建会话审计摘要。"""

        session = self._vm.facade.get_session(session_id)
        if session is None:
            return ""
        trace = self._vm.facade.get_trace(session_id)
        body = "<br>".join(
            [
                rich_text.field("工作流: ", session.workflow_id),
                rich_text.field("状态: ", session.status.value),
                rich_text.field("步骤数: ", len(session.steps)),
                rich_text.field("轨迹记录: ", len(trace)),
            ]
        )
        return rich_text.panel("会话审计", body)

    @staticmethod
    def _workflow_info_html(summary) -> str:
        """格式化工作流绑定设备摘要。"""

        actions = ", ".join(summary.actions or []) or "-"
        window_bits = []
        if summary.title_contains:
            label = "标题匹配" if summary.match_mode == "equals" else "标题包含"
            window_bits.append(f"{label}: {summary.title_contains}")
        if summary.process_name:
            window_bits.append(f"进程: {summary.process_name}")
        window_text = "\n".join(window_bits) if window_bits else "-"
        device_status = (
            summary.status_text
            if summary.device_found
            else f"{summary.status_text} ({summary.anchor_profile or '-'})"
        )
        cards = [
            rich_text.info_card(
                "基础信息",
                [
                    ("工作流: ", summary.workflow_id),
                    ("状态: ", summary.lifecycle_state),
                    ("模板: ", summary.template_label),
                ],
            ),
            rich_text.info_card(
                "设备评估",
                [
                    ("绑定设备: ", summary.anchor_profile or "-"),
                    ("配置状态: ", device_status),
                    ("窗口: ", window_text if summary.device_found else "-"),
                ],
            ),
            rich_text.info_card(
                "能力评估",
                [
                    ("锚点: ", summary.anchor_count if summary.device_found else 0),
                    ("OCR观测: ", summary.ocr_anchor_count if summary.device_found else 0),
                    ("动作: ", actions if summary.device_found else "-"),
                ],
            ),
        ]
        return rich_text.panel(
            "工作流绑定设备",
            rich_text.info_grid(cards),
            status="success" if summary.device_found else "warning",
        )

    @staticmethod
    def _observation_html(event: RuntimeEvent) -> str:
        """构建观察事件文本。"""

        payload = event.payload
        expected = payload.get("expected_text") or payload.get("expected_candidates")
        rule = rich_text.ocr_rule(payload.get("match_mode"), expected)
        body = "<br>".join(
            [
                rich_text.field("步骤: ", payload.get("step_id")),
                rich_text.field("期望规则: ", rule),
                rich_text.field("实际识别: ", payload.get("actual_text") or "-"),
                rich_text.field("匹配: ", payload.get("matched")),
                rich_text.field("尝试: ", payload.get("attempts")),
                rich_text.field(
                    "耗时: ",
                    f"{float(payload.get('elapsed_seconds') or 0):.2f}s",
                ),
                rich_text.field("截图: ", payload.get("screenshot_path") or "-"),
            ]
        )
        return rich_text.panel("最新 OCR 观测", body)
