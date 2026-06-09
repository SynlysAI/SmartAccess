"""Workflow journey landing page."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from smartaccess.desktop.journey_projection import build_journey_projection
from smartaccess.desktop.shell import theme as t
from smartaccess.desktop.viewmodels.dashboard_vm import DashboardViewModel
from smartaccess.desktop.widgets.cards import Card, hint_label, page_header, section_title
from smartaccess.desktop.widgets.workflow_journey import WorkflowJourneyGraph


class JourneyPage(QWidget):
    navigate_requested = pyqtSignal(int)

    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = DashboardViewModel(facade, self)
        self._projection = None
        self._stage_map: dict[str, int] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)
        root.addWidget(page_header("流程引导", "按主路径完成设备接入、工作流设计、模板发布与执行闭环。"))

        hero = Card(flush=True)
        self._graph = WorkflowJourneyGraph()
        self._graph.stage_clicked.connect(self._go_to_stage)
        hero.add(self._graph)
        root.addWidget(hero, 1)

        footer = Card()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        self._summary = QLabel("当前进度：尚未开始，请先完成设备接入与校准。")
        self._summary.setObjectName("Body")
        self._summary.setWordWrap(True)
        row.addWidget(self._summary, 1)
        self._cta = QPushButton("继续到下一步")
        self._cta.clicked.connect(self._continue_to_next)
        row.addWidget(self._cta)
        footer.body().addLayout(row)
        root.addWidget(footer)

        self._reload()

    def on_show(self) -> None:
        self._reload()

    def _reload(self) -> None:
        dashboard = self._vm.projection()
        workflows = self._vm.facade.list_workflows()
        workflow_checks = {
            workflow.metadata.workflow_id: self._vm.facade.standardize(workflow)
            for workflow in workflows
        }
        templates = self._vm.facade.list_templates()
        self._projection = build_journey_projection(dashboard, workflows, workflow_checks, templates)
        self._graph.set_projection(self._projection)
        self._stage_map = {
            stage.stage_id: stage.target_page_index for stage in self._projection.stages
        }
        self._summary.setText(self._projection.summary)
        self._cta.setText(self._projection.cta_label)
        self._cta.setStyleSheet(
            "background:%s;color:%s;border-radius:12px;padding:12px 20px;font-weight:700;"
            % (t.PRIMARY, t.INK)
        )

    def _go_to_stage(self, stage_id: str) -> None:
        target = self._stage_map.get(stage_id)
        if target is not None:
            self.navigate_requested.emit(target)

    def _continue_to_next(self) -> None:
        if self._projection is not None:
            self.navigate_requested.emit(self._projection.cta_target_page_index)
