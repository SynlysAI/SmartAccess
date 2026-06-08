"""Run monitoring page: timeline, readings, live log, and run controls."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.viewmodels.base import EventRelay
from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel
from smartaccess.desktop.widgets.cards import Card, page_header, section_title
from smartaccess.desktop.widgets.log_view import LogView
from smartaccess.desktop.widgets.status_pill import StatusPill
from smartaccess.desktop.widgets.timeline import Timeline


class MonitoringPage(QWidget):
    def __init__(self, facade, relay: EventRelay, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._vm = MonitoringViewModel(facade, relay, self)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(page_header("运行监控", "当前步骤、真实截图/识别、日志流与异常恢复"))

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self._workflow = QComboBox()
        self._start = QPushButton("发起运行")
        self._start.clicked.connect(self._on_start)
        self._state = StatusPill("idle")
        controls.addWidget(QLabel("工作流"))
        controls.addWidget(self._workflow, 1)
        controls.addWidget(self._start)
        controls.addWidget(self._state)
        root.addLayout(controls)

        body = QHBoxLayout()
        body.setSpacing(16)

        timeline_card = Card()
        timeline_card.add(section_title("步骤时间线"))
        self._timeline = Timeline()
        timeline_card.add(self._timeline)

        center_card = Card()
        tabs = QTabWidget()
        obs_tab = QWidget()
        obs_layout = QVBoxLayout(obs_tab)
        self._reading = QLabel("尚无识别结果")
        self._reading.setWordWrap(True)
        self._reading.setStyleSheet("color: #4b5563;")
        obs_layout.addWidget(self._reading)
        self._shot = QLabel("最新截图会在真实 provider 执行后写入 run artifacts")
        self._shot.setWordWrap(True)
        self._shot.setStyleSheet("background:#f3f4f6; border:1px dashed #d1d5db; color:#6b7280; padding:32px; border-radius:8px;")
        obs_layout.addWidget(self._shot)
        audit_tab = QWidget()
        audit_layout = QVBoxLayout(audit_tab)
        self._audit = QLabel("暂无审计摘要")
        self._audit.setWordWrap(True)
        self._audit.setStyleSheet("color:#4b5563;")
        audit_layout.addWidget(self._audit)
        audit_layout.addStretch(1)
        tabs.addTab(obs_tab, "观测")
        tabs.addTab(audit_tab, "审计")
        center_card.add(tabs)

        log_card = Card()
        log_card.add(section_title("运行日志流"))
        self._log = LogView()
        log_card.add(self._log)

        body.addWidget(timeline_card, 2)
        body.addWidget(center_card, 2)
        body.addWidget(log_card, 3)
        root.addLayout(body, 1)

        self._wire_vm()
        self._reload()

    def _wire_vm(self) -> None:
        self._vm.steps_reset.connect(self._timeline.reset)
        self._vm.step_changed.connect(self._timeline.set_step_status)
        self._vm.log_line.connect(self._log.append_line)
        self._vm.run_state.connect(self._state.set_status)
        self._vm.reading.connect(self._reading.setText)
        self._vm.audit.connect(self._audit.setText)

    def _reload(self) -> None:
        self._workflow.clear()
        self._workflows = self._facade.list_workflows()
        for wf in self._workflows:
            self._workflow.addItem(wf.metadata.workflow_id)

    def _on_start(self) -> None:
        idx = self._workflow.currentIndex()
        if idx < 0 or idx >= len(self._workflows):
            self._log.append_line("没有可运行的工作流，请先在工作流设计页生成。")
            return
        self._state.set_status("running")
        self._vm.start(self._workflows[idx])
