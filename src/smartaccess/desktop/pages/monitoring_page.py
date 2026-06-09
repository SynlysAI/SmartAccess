"""Run monitoring page: controls, step timeline, observations, live log, audit."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
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
        root.addWidget(page_header("运行监控", "当前步骤、真实截图/识别、日志流与异常恢复"))

        controls = self._build_controls()
        root.addWidget(controls)

        body = QHBoxLayout()
        body.setSpacing(16)

        timeline_card = Card()
        timeline_card.add(section_title("步骤时间线"))
        timeline_card.add(hint_label("○ 待执行 · ◐ 执行中 · ◑ 已观测 · ● 成功 · ▲ 阻断 · ✕ 失败"))
        self._timeline = Timeline()
        timeline_card.add(self._timeline)

        body.addWidget(timeline_card, 2)
        body.addWidget(self._build_run_tabs(), 5)
        root.addLayout(body, 1)

        self._wire_vm()
        self._reload()

    def on_show(self) -> None:
        self._reload()

    def _build_controls(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(10)
        self._workflow = QComboBox()
        self._start = QPushButton("发起运行")
        self._start.clicked.connect(self._on_start)
        self._state = StatusPill("idle")
        label = QLabel("工作流")
        label.setObjectName("Body")
        row.addWidget(label)
        row.addWidget(self._workflow, 1)
        row.addWidget(self._start)
        row.addWidget(self._state)
        card.body().addLayout(row)
        return card

    def _build_run_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_center(), "观测与审计")

        log_card = Card()
        log_card.add(section_title("运行日志流"))
        self._log = LogView()
        log_card.add(self._log)
        tabs.addTab(log_card, "日志")
        return tabs

    def _build_center(self) -> QWidget:
        center = Card(flush=True)

        obs_section = CollapsibleSection("观测结果", accent=t.PRIMARY)
        obs_section.add(hint_label(
            "运行时根据锚点配置的识别方式进行观测：OCR 读取文字、Template 比对模板图、"
            "Color 检测颜色状态、Presence 判断元素是否存在。置信度 < 60% 时会触发重试。"
        ))
        self._reading = rich_text(QLabel("尚无识别结果。"))
        obs_section.add(self._reading)

        # Recognition explanation guide
        guide = QLabel(
            f"<div style='color:{t.INK_MUTED};font-size:12px;margin-top:4px;'>"
            "<b>🔍 识别结果解读：</b>"
            "<ul style='margin:4px 0;'>"
            "<li><b>OCR 文本识别</b> — 从 ROI 截图读取文字。text=识别到的文本，confidence=PaddleOCR 置信度 (0-1)。"
            "低置信度可能因截图模糊或文字被遮挡。</li>"
            "<li><b>Template 模板匹配</b> — 与校准基准图比对。text=matched/no_match，confidence=相似度分数。"
            "分数 ≥ 0.8 为匹配，低于阈值触发异常。</li>"
            "<li><b>Color 颜色识别</b> — 采样 ROI 主色。text=matched/no_match 或色值(#RRGGBB)，"
            "confidence=与参考色的近似度。distance 为 HSV 距离，≤ 容差即为匹配。</li>"
            "<li><b>Presence 存在性检测</b> — 判断控件是否出现。text=present/missing，"
            "confidence=前景像素占比。</li>"
            "</ul></div>"
        )
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.TextFormat.RichText) if hasattr(Qt, "TextFormat") else None
        obs_section.add(guide)

        self._shot = QLabel("最新截图会在真实 provider 执行后写入 run artifacts。")
        self._shot.setWordWrap(True)
        self._shot.setStyleSheet(
            f"background:{t.CANVAS}; border:1px dashed {t.HAIRLINE_STRONG};"
            f" color:{t.INK_SUBTLE}; padding:28px; border-radius:8px;"
        )
        obs_section.add(self._shot)
        center.add(obs_section)

        audit_section = CollapsibleSection("审计摘要", accent=t.SUCCESS, expanded=False)
        self._audit = rich_text(QLabel("暂无审计摘要。"))
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
        self._vm.audit.connect(self._audit.setText)

    def _clear_run_display(self) -> None:
        self._log.clear_log()
        self._reading.setText("尚无识别结果。")
        self._audit.setText("暂无审计摘要。")
        self._shot.setText("最新截图会在真实 provider 执行后写入 run artifacts。")

    def _reload(self) -> None:
        current = self._workflow.currentText()
        self._workflow.clear()
        self._workflows = self._facade.list_workflows()
        for wf in self._workflows:
            self._workflow.addItem(wf.metadata.workflow_id)
        if current:
            idx = self._workflow.findText(current)
            if idx >= 0:
                self._workflow.setCurrentIndex(idx)

    def _on_start(self) -> None:
        idx = self._workflow.currentIndex()
        if idx < 0 or idx >= len(self._workflows):
            self._log.append_line("没有可运行的工作流，请先在工作流设计页生成。")
            return
        self._state.set_status("running")
        self._vm.start(self._workflows[idx])
