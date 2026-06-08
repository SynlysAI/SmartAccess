"""Workbench home: task queue, device status, recent runs, incident alerts."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.viewmodels.dashboard_vm import DashboardViewModel
from smartaccess.desktop.widgets.cards import Card, StatCard, page_header, section_title


class DashboardPage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = DashboardViewModel(facade, self)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(page_header("工作台首页", "任务队列、设备状态、模板版本、最近运行与待处理异常"))

        stats = QHBoxLayout()
        stats.setSpacing(16)
        self._stat_devices = StatCard("真实接入设备")
        self._stat_local_templates = StatCard("本地模板")
        self._stat_cloud_templates = StatCard("云端模板")
        self._stat_runs = StatCard("最近运行")
        self._stat_incidents = StatCard("待处理异常")
        self._stat_outbox = StatCard("待补传")
        for card in (
            self._stat_devices,
            self._stat_local_templates,
            self._stat_cloud_templates,
            self._stat_runs,
            self._stat_incidents,
            self._stat_outbox,
        ):
            stats.addWidget(card)
        root.addLayout(stats)

        lists = QGridLayout()
        lists.setSpacing(16)
        runs_card = Card()
        runs_card.add(section_title("最近运行记录"))
        self._runs_list = QListWidget()
        runs_card.add(self._runs_list)
        incidents_card = Card()
        incidents_card.add(section_title("异常与待补传告警"))
        self._incidents_list = QListWidget()
        incidents_card.add(self._incidents_list)
        lists.addWidget(runs_card, 0, 0)
        lists.addWidget(incidents_card, 0, 1)
        root.addLayout(lists, 1)

        refresh = QPushButton("刷新")
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self.refresh)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(refresh)
        root.addLayout(row)

        self.refresh()

    def refresh(self) -> None:
        proj = self._vm.projection()
        self._stat_devices.set_value(str(len(proj.devices)))
        self._stat_local_templates.set_value(str(proj.local_template_count))
        cloud_value = str(proj.cloud_template_count) if proj.cloud_templates_available else "离线"
        self._stat_cloud_templates.set_value(cloud_value)
        self._stat_runs.set_value(str(len(proj.recent_runs)))
        self._stat_incidents.set_value(str(len(proj.incidents)))
        self._stat_outbox.set_value(str(proj.outbox_pending))

        self._runs_list.clear()
        for run in proj.recent_runs:
            self._runs_list.addItem(f"{run.session_id}  ·  {run.workflow_id}  ·  {run.status}")
        if not proj.recent_runs:
            self._runs_list.addItem("暂无运行记录")

        self._incidents_list.clear()
        for inc in proj.incidents:
            self._incidents_list.addItem(f"! {inc.type}  ·  {inc.detail}")
        if proj.template_sync_failed:
            self._incidents_list.addItem(f"! 模板发布/同步失败 {proj.template_sync_failed} 条")
        if proj.outbox_failed:
            self._incidents_list.addItem(f"! 平台补传失败 {proj.outbox_failed} 条")
        if self._incidents_list.count() == 0:
            self._incidents_list.addItem("无待处理异常")
