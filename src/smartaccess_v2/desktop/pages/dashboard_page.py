"""运行概览页面。"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartaccess_v2.desktop.viewmodels.dashboard_vm import DashboardViewModel
from smartaccess_v2.runtime.application.facade import RuntimeFacade


class DashboardPage(QWidget):
    """设备、模板、运行和异常的概览页面。"""

    def __init__(self, facade: RuntimeFacade, parent: QWidget | None = None) -> None:
        """初始化概览页面。"""

        super().__init__(parent)
        self._vm = DashboardViewModel(facade, self)
        self._vm.changed.connect(self._refresh)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel("运行概览")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self._stats = QGridLayout()
        root.addLayout(self._stats)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("Secondary")
        refresh_btn.clicked.connect(self._refresh)
        root.addWidget(refresh_btn)

        self._runs = QTableWidget(0, 3)
        self._runs.setHorizontalHeaderLabels(("会话", "工作流", "状态"))
        self._runs.verticalHeader().setVisible(False)
        self._runs.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._runs, 1)

        self._incidents = QTableWidget(0, 4)
        self._incidents.setHorizontalHeaderLabels(("异常", "会话", "类型", "详情"))
        self._incidents.verticalHeader().setVisible(False)
        self._incidents.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._incidents, 1)
        self._refresh()

    def closeEvent(self, event) -> None:  # noqa: N802
        """页面关闭时释放订阅。"""

        self._vm.close()
        super().closeEvent(event)

    def on_show(self) -> None:
        """页面显示时刷新概览。"""

        self._refresh()

    def _refresh(self) -> None:
        """刷新概览数据。"""

        projection = self._vm.dashboard()
        stats = {
            "设备": len(projection.devices),
            "工作流": projection.workflow_count,
            "模板": projection.template_count,
            "本地模板": projection.local_template_count,
            "云端模板": projection.cloud_template_count,
            "模板错误": projection.template_sync_failed,
            "补传待处理": projection.outbox_pending,
            "补传失败": projection.outbox_failed,
        }
        self._refresh_stats(stats)
        self._fill_table(
            self._runs,
            projection.recent_runs,
            ("session_id", "workflow_id", "status"),
        )
        self._fill_table(
            self._incidents,
            projection.incidents,
            ("incident_id", "session_id", "type", "detail"),
        )

    def _refresh_stats(self, stats: dict[str, int]) -> None:
        """刷新统计标签。"""

        while self._stats.count():
            item = self._stats.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for index, (label, value) in enumerate(stats.items()):
            name = QLabel(label)
            name.setObjectName("PageHint")
            count = QLabel(str(value))
            count.setObjectName("PageTitle")
            row = index // 4
            column = (index % 4) * 2
            self._stats.addWidget(name, row, column)
            self._stats.addWidget(count, row, column + 1)

    @staticmethod
    def _fill_table(
        table: QTableWidget,
        rows: list[dict[str, str]],
        fields: tuple[str, ...],
    ) -> None:
        """用字典列表填充表格。"""

        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, field in enumerate(fields):
                table.setItem(row_index, column, QTableWidgetItem(row.get(field, "")))
