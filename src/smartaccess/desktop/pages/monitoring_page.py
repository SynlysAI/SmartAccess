"""Run monitoring page: controls, step timeline, observations, live log, audit."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.shell import theme as t
from smartaccess.desktop.viewmodels.base import EventRelay
from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel
from smartaccess.desktop.widgets.cards import (
    Card,
    CollapsibleSection,
    hint_label,
    page_header,
    rich_text,
    section_title,
)
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
        root.addWidget(
            page_header(
                "运行监控",
                "查看步骤时间线、识别结果、截图落盘位置、日志流与审计摘要。",
            )
        )

        root.addWidget(self._build_controls())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_timeline_panel())
        splitter.addWidget(self._build_run_tabs())
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 13)
        splitter.setStretchFactor(1, 25)
        splitter.setSizes([520, 980])
        root.addWidget(splitter, 1)

        self._wire_vm()
        self._set_running_controls(False)
        self._reload()

    def on_show(self) -> None:
        self._reload()

    def _build_controls(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(10)
        self._workflow = QComboBox()
        self._start = QPushButton("开始")
        self._start.clicked.connect(self._on_start)
        self._stop = QPushButton("停止")
        self._stop.setObjectName("Ghost")
        self._stop.clicked.connect(self._on_stop)
        self._cancel = QPushButton("取消")
        self._cancel.setObjectName("Ghost")
        self._cancel.clicked.connect(self._on_cancel)
        self._state = StatusPill("idle")
        label = QLabel("工作流")
        label.setObjectName("Body")
        row.addWidget(label)
        row.addWidget(self._workflow, 1)
        row.addWidget(self._start)
        row.addWidget(self._stop)
        row.addWidget(self._cancel)
        row.addWidget(self._state)
        card.body().addLayout(row)
        return card

    def _build_timeline_panel(self) -> QWidget:
        card = Card()
        card.add(section_title("步骤时间线"))
        card.add(
            hint_label(
                "左侧时间线已放宽，步骤详情会自动换行，方便查看 anchor_id、value 和状态时间。"
            )
        )
        self._timeline = Timeline()
        card.add(self._timeline)
        return card

    def _build_run_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_center(), "观测与审计")

        log_card = Card()
        log_card.add(section_title("运行日志"))
        self._log = LogView()
        log_card.add(self._log)
        tabs.addTab(log_card, "日志")
        return tabs

    def _build_center(self) -> QWidget:
        center = Card(flush=True)

        obs_section = CollapsibleSection("观测结果", accent=t.PRIMARY)
        obs_section.add(
            hint_label(
                "有 OCR 条件的步骤会轮询锚点观察区域；普通步骤只执行固定等待。"
            )
        )
        self._reading = rich_text(QLabel("暂无识别结果。"))
        obs_section.add(self._reading)

        guide = QLabel(
            f"<div style='color:{t.INK_MUTED};font-size:12px;margin-top:4px;'>"
            "<b>识别结果说明</b>"
            "<ul style='margin:6px 0 0 16px;'>"
            "<li><b>OCR</b>: 读出 ROI 内文字，text 为识别内容，confidence 为置信度。</li>"
            "<li><b>固定等待</b>: match_mode 为 none 时不会做 OCR 校验，trace 中 matched 为空。</li>"
            "<li><b>OCR 轮询</b>: expected_text 或 not_empty 会形成校验标准，并记录实测值。</li>"
            "</ul></div>"
        )
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.TextFormat.RichText)
        obs_section.add(guide)

        self._shot = rich_text(QLabel("最新截图路径会显示在这里。"))
        self._shot.setStyleSheet(
            f"background:{t.CANVAS}; border:1px dashed {t.HAIRLINE_STRONG};"
            f" color:{t.INK_SUBTLE}; padding:20px; border-radius:8px;"
        )
        obs_section.add(self._shot)
        center.add(obs_section)

        audit_section = CollapsibleSection("步骤审计", accent=t.SUCCESS, expanded=True)
        self._audit = QTextBrowser()
        self._audit.setObjectName("LogView")
        self._audit.setOpenExternalLinks(True)
        self._audit.setReadOnly(True)
        self._audit.setMinimumHeight(260)
        self._audit.setHtml("暂无步骤审计。")
        audit_section.add(self._audit)
        center.add(audit_section)
        center.body().addStretch(1)
        return center

    def _wire_vm(self) -> None:
        self._vm.steps_reset.connect(self._timeline.reset_steps)
        self._vm.step_changed.connect(self._timeline.set_step_status)
        self._vm.clear_display.connect(self._clear_run_display)
        self._vm.log_line.connect(self._log.append_line)
        self._vm.run_state.connect(self._state.set_status)
        self._vm.reading.connect(self._reading.setText)
        self._vm.audit.connect(self._audit.setHtml)
        self._vm.shot.connect(self._shot.setText)
        self._vm.run_state.connect(self._on_run_state_changed)

    def _set_running_controls(self, running: bool) -> None:
        self._start.setEnabled(not running)
        self._workflow.setEnabled(not running)
        self._stop.setEnabled(running)
        self._cancel.setEnabled(running)

    def _on_run_state_changed(self, state: str) -> None:
        running = state in {"running", "run.ready", "run.step.started", "stopping", "cancelling"}
        if state in {"run.completed", "run.failed"}:
            running = False
        self._set_running_controls(running)

    def _clear_run_display(self) -> None:
        self._log.clear_log()
        self._reading.setText("暂无识别结果。")
        self._audit.setHtml("暂无步骤审计。")
        self._shot.setText("最新截图路径会显示在这里。")

    def _reload(self) -> None:
        current = self._workflow.currentText()
        self._workflow.clear()
        self._workflows = self._facade.list_workflows()
        for workflow in self._workflows:
            self._workflow.addItem(workflow.metadata.workflow_id)
        if current:
            idx = self._workflow.findText(current)
            if idx >= 0:
                self._workflow.setCurrentIndex(idx)

    def _on_start(self) -> None:
        idx = self._workflow.currentIndex()
        if idx < 0 or idx >= len(self._workflows):
            self._log.append_line("没有可运行的工作流，请先到工作流设计页生成或保存。")
            return
        self._state.set_status("running")
        self._set_running_controls(True)
        self._vm.start(self._workflows[idx])

    def _on_stop(self) -> None:
        self._vm.stop(cancel=False)

    def _on_cancel(self) -> None:
        self._vm.stop(cancel=True)
