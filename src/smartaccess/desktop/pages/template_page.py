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
from smartaccess.desktop.viewmodels.template_vm import (
    DEFAULT_TEMPLATE_VERSION,
    TemplateViewModel,
)
from smartaccess.runtime.application.facade import RuntimeFacade
from smartaccess.runtime.application.template_service import TemplateRecord


class TemplatePage(QWidget):
    """模板发布、搜索和平台同步页面。"""

    HEADERS = ("模板", "版本", "工作流", "状态", "设备", "来源", "发布时间", "错误")

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
        self._table.setColumnWidth(6, 200)
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
        row.addWidget(QLabel("设备:"))
        self._anchor_combo = QComboBox()
        self._anchor_combo.setMinimumWidth(180)
        self._anchor_combo.currentIndexChanged.connect(self._reload_workflows)
        row.addWidget(self._anchor_combo)
        row.addWidget(QLabel("工作流:"))
        self._workflow_combo = QComboBox()
        self._workflow_combo.setMinimumWidth(280)
        row.addWidget(self._workflow_combo)
        row.addWidget(QLabel("模板ID:"))
        self._template_id = QLineEdit()
        self._template_id.setMinimumWidth(120)
        self._template_id.setPlaceholderText("默认工作流ID")
        row.addWidget(self._template_id)
        row.addWidget(QLabel("版本:"))
        self._template_version = QLineEdit()
        self._template_version.setMinimumWidth(80)
        self._template_version.setPlaceholderText(DEFAULT_TEMPLATE_VERSION)
        row.addWidget(self._template_version)
        publish_btn = QPushButton("发布")
        publish_btn.clicked.connect(self._publish)
        row.addWidget(publish_btn)
        refresh_btn = QPushButton("同步云端")
        refresh_btn.setObjectName("Secondary")
        refresh_btn.clicked.connect(self._refresh_cloud)
        row.addWidget(refresh_btn)
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
            template_id, template_version = self._template_identity(str(workflow_id))
            if self._vm.template_exists(template_id, template_version):
                choice = self._confirm_existing_template(template_id, template_version)
                if choice == "cancel":
                    return
                if choice == "new_version":
                    template_version = self._vm.next_template_version(template_id)
            record = self._vm.publish(
                str(workflow_id),
                template_id=template_id,
                template_version=template_version,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "发布失败", str(exc))
            return
        QMessageBox.information(
            self,
            "发布完成",
            f"{record.identity.template_id}@{record.identity.template_version}",
        )

    def _template_identity(self, workflow_id: str) -> tuple[str, str]:
        """返回发布页填写或自动生成的模板身份。

        Args:
            workflow_id: 当前要发布的工作流 ID。

        Returns:
            模板 ID 与模板版本。
        """

        template_id = self._template_id.text().strip() or workflow_id
        template_version = (
            self._template_version.text().strip() or DEFAULT_TEMPLATE_VERSION
        )
        return template_id, template_version

    def _confirm_existing_template(
        self,
        template_id: str,
        template_version: str,
    ) -> str:
        """确认已存在模板版本的处理方式。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            用户选择的处理方式。
        """

        msg = QMessageBox(self)
        msg.setWindowTitle("模板版本已存在")
        msg.setText(f"模板 {template_id}@{template_version} 已存在。")
        msg.setInformativeText("请选择覆盖当前版本，或自动发布为新版本。")
        overwrite_btn = msg.addButton("覆盖", QMessageBox.ButtonRole.AcceptRole)
        new_version_btn = msg.addButton("发布新版本", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(new_version_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == overwrite_btn:
            return "overwrite"
        if clicked == new_version_btn:
            return "new_version"
        if clicked == cancel_btn:
            return "cancel"
        return "cancel"

    def _refresh_cloud(self) -> None:
        """刷新云端模板索引。"""

        self._vm.refresh_cloud()

    def _delete(self) -> None:
        """删除选中的模板版本。"""

        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "删除模板", "请先选择模板版本")
            return
        identity = f"{record.identity.template_id}@{record.identity.template_version}"
        msg = QMessageBox(self)
        msg.setWindowTitle("删除模板")
        msg.setText(f"确认删除 {identity}？")
        msg.setInformativeText("选择删除范围：")
        local_btn = msg.addButton("仅删除本地", QMessageBox.ButtonRole.AcceptRole)
        cloud_btn = msg.addButton("同时删除云端", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(cancel_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == cancel_btn:
            return
        try:
            if clicked == cloud_btn:
                self._vm.delete_cloud_first(
                    record.identity.template_id,
                    record.identity.template_version,
                    force=True,
                )
            else:
                self._vm.delete(
                    record.identity.template_id,
                    record.identity.template_version,
                    force=True,
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "删除失败", str(exc))

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
            record.workflow_id,
            record.status.value,
            record.anchor_profile,
            record.source,
            record.published_at,
            record.error,
        )
