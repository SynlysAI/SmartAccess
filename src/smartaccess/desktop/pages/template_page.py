"""模板与平台页面。"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.widgets.cards import create_card
from smartaccess.desktop.widgets.table_style import configure_data_table
from smartaccess.desktop.viewmodels.template_vm import TemplateViewModel
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.runtime.application.template_service import TemplateRecord


class TemplatePage(QWidget):
    """模板发布、搜索和平台同步页面。"""

    HEADERS = ("模板", "版本", "状态", "设备", "来源", "发布时间", "错误")

    def __init__(self, facade: RuntimeFacade, parent: QWidget | None = None) -> None:
        """初始化模板页面。"""

        super().__init__(parent)
        self._vm = TemplateViewModel(facade, self)
        self._vm.changed.connect(self._refresh)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        root.addLayout(self._build_header())

        filter_card, filter_layout = create_card(margins=(14, 14, 14, 14), spacing=10)
        filter_layout.addLayout(self._build_filters())
        root.addWidget(filter_card)

        table_card, table_layout = create_card(margins=(0, 0, 0, 0), spacing=0)
        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        configure_data_table(self._table, row_height=38, stretch_last=True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table)
        root.addWidget(table_card, 1)
        self._reload_instruments()
        self._reload_workflows()
        self._refresh()

    def on_show(self) -> None:
        """页面显示时刷新数据。"""

        self._reload_instruments()
        self._reload_workflows()
        self._refresh()

    def _build_header(self) -> QHBoxLayout:
        """构建顶部操作区。"""

        row = QHBoxLayout()
        title = QLabel("模板/平台")
        title.setObjectName("PageTitle")
        row.addWidget(title)
        row.addStretch(1)
        self._anchor_combo = QComboBox()
        self._anchor_combo.setMinimumWidth(180)
        self._anchor_combo.currentIndexChanged.connect(self._reload_workflows)
        row.addWidget(self._anchor_combo)
        self._workflow_combo = QComboBox()
        self._workflow_combo.setMinimumWidth(280)
        row.addWidget(self._workflow_combo)
        publish_btn = QPushButton("发布")
        publish_btn.clicked.connect(self._publish)
        row.addWidget(publish_btn)
        update_btn = QPushButton("更新设备")
        update_btn.setObjectName("Secondary")
        update_btn.clicked.connect(self._update_anchor_profile)
        row.addWidget(update_btn)
        rollback_btn = QPushButton("回滚")
        rollback_btn.setObjectName("Secondary")
        rollback_btn.clicked.connect(self._rollback)
        row.addWidget(rollback_btn)
        refresh_btn = QPushButton("刷新云端")
        refresh_btn.setObjectName("Secondary")
        refresh_btn.clicked.connect(self._refresh_cloud)
        row.addWidget(refresh_btn)
        sync_btn = QPushButton("补传")
        sync_btn.setObjectName("Secondary")
        sync_btn.clicked.connect(self._sync_outbox)
        row.addWidget(sync_btn)
        delete_btn = QPushButton("删除")
        delete_btn.setObjectName("Danger")
        delete_btn.clicked.connect(self._delete)
        row.addWidget(delete_btn)
        return row

    def _build_filters(self) -> QFormLayout:
        """构建搜索过滤区。"""

        form = QFormLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("按模板、版本、设备、错误搜索")
        self._query.textChanged.connect(self._refresh)
        self._status = QComboBox()
        for label, value in (
            ("全部", ""),
            ("Draft", "draft"),
            ("Published", "published"),
            ("Superseded", "superseded"),
        ):
            self._status.addItem(label, value)
        self._status.currentIndexChanged.connect(self._refresh)
        form.addRow("搜索", self._query)
        form.addRow("状态", self._status)
        return form

    def _reload_workflows(self) -> None:
        """刷新工作流下拉框，按当前选中的设备过滤。

        未选设备（占位项 data 为空）时展示全部工作流。
        """

        current = self._workflow_combo.currentData()
        anchor_profile = self._anchor_combo.currentData()
        self._workflow_combo.clear()
        for workflow in self._vm.workflows():
            if anchor_profile and workflow.metadata.anchor_profile != anchor_profile:
                continue
            workflow_id = workflow.metadata.workflow_id
            self._workflow_combo.addItem(workflow_id, workflow_id)
        index = self._workflow_combo.findData(current)
        if index >= 0:
            self._workflow_combo.setCurrentIndex(index)

    def _reload_instruments(self) -> None:
        """刷新设备锚点配置下拉框。"""

        current = self._anchor_combo.currentData()
        self._anchor_combo.blockSignals(True)
        self._anchor_combo.clear()
        self._anchor_combo.addItem("选择设备", "")
        for profile_id in self._vm.instruments():
            self._anchor_combo.addItem(profile_id, profile_id)
        index = self._anchor_combo.findData(current)
        if index >= 0:
            self._anchor_combo.setCurrentIndex(index)
        self._anchor_combo.blockSignals(False)

    def _refresh(self) -> None:
        """刷新模板表格。"""

        records = self._vm.templates(
            query=self._query.text(),
            status=str(self._status.currentData() or ""),
        )
        self._table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = self._record_values(record)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record)
                self._table.setItem(row, column, item)

    def _publish(self) -> None:
        """发布当前工作流为模板。"""

        workflow_id = self._workflow_combo.currentData()
        if not workflow_id:
            QMessageBox.warning(self, "无法发布", "请先保存工作流")
            return
        try:
            record = self._vm.publish(str(workflow_id))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "发布失败", str(exc))
            return
        QMessageBox.information(
            self,
            "发布完成",
            f"{record.identity.template_id}@{record.identity.template_version}",
        )

    def _refresh_cloud(self) -> None:
        """刷新云端模板索引。"""

        self._vm.refresh_cloud()

    def _update_anchor_profile(self) -> None:
        """更新选中模板版本的设备锚点配置。"""

        record = self._selected_record()
        anchor_profile = self._anchor_combo.currentData()
        if record is None:
            QMessageBox.information(self, "更新设备", "请先选择模板版本")
            return
        if not anchor_profile:
            QMessageBox.information(self, "更新设备", "请先选择设备")
            return
        try:
            self._vm.update_anchor_profile(
                record.identity.template_id,
                record.identity.template_version,
                str(anchor_profile),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "更新失败", str(exc))

    def _rollback(self) -> None:
        """回滚选中的模板版本。"""

        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "回滚模板", "请先选择模板版本")
            return
        reply = QMessageBox.question(
            self,
            "回滚模板",
            f"确认回滚到 {record.identity.template_id}@{record.identity.template_version}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._vm.rollback(
                record.identity.template_id,
                record.identity.template_version,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "回滚失败", str(exc))

    def _sync_outbox(self) -> None:
        """同步平台补传队列。"""

        self._vm.sync_outbox()

    def _delete(self) -> None:
        """删除选中的模板版本。"""

        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "删除模板", "请先选择模板版本")
            return
        reply = QMessageBox.question(
            self,
            "删除模板",
            f"确认删除 {record.identity.template_id}@{record.identity.template_version}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._vm.delete(
            record.identity.template_id,
            record.identity.template_version,
            force=True,
        )

    def _selected_record(self) -> TemplateRecord | None:
        """返回当前选中的模板记录。"""

        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    @staticmethod
    def _record_values(record: TemplateRecord) -> tuple[str, ...]:
        """返回表格行字段。"""

        return (
            record.identity.template_id,
            record.identity.template_version,
            record.status.value,
            record.anchor_profile,
            record.source,
            record.published_at,
            record.error,
        )
