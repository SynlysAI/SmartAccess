"""Template library page: list versions, publish, roll back."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.viewmodels.template_vm import TemplateViewModel
from smartaccess.desktop.widgets.cards import Card, page_header, section_title


class TemplatePage(QWidget):
    def __init__(self, facade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = TemplateViewModel(facade, self)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(page_header("模板库", "本地模板、SpecLabOS 云端版本、发布状态与回滚/复用"))

        summary = QHBoxLayout()
        self._summary = QLabel("模板版本：本地 0 · 云端 离线")
        self._summary.setStyleSheet("color:#4b5563;")
        refresh_cloud = QPushButton("刷新云端")
        refresh_cloud.setObjectName("Ghost")
        refresh_cloud.clicked.connect(self._refresh_cloud)
        summary.addWidget(self._summary)
        summary.addStretch(1)
        summary.addWidget(refresh_cloud)
        root.addLayout(summary)

        body = QHBoxLayout()
        body.setSpacing(16)

        left = Card()
        left.add(section_title("发布标准模板"))
        self._workflow = QComboBox()
        left.add(self._workflow)
        self._template_id = QLineEdit()
        self._template_id.setPlaceholderText("template_id（留空时使用工作流 ID）")
        left.add(self._template_id)
        self._version = QLineEdit()
        self._version.setPlaceholderText("template_version，如 1.0.0")
        left.add(self._version)
        publish = QPushButton("发布到 SpecLabOS 模板中心")
        publish.clicked.connect(self._publish)
        left.add(publish)

        right = Card()
        right.add(section_title("模板版本"))
        self._tree = QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(["模板 ID", "版本", "状态", "来源", "适用仪器", "错误"])
        right.add(self._tree)
        rollback = QPushButton("回滚到所选版本")
        rollback.setObjectName("Ghost")
        rollback.clicked.connect(self._rollback)
        right.add(rollback)

        body.addWidget(left, 2)
        body.addWidget(right, 3)
        root.addLayout(body, 1)

        self._reload()

    def _reload(self) -> None:
        self._workflow.clear()
        self._workflows = self._vm.publishable_workflows()
        for wf in self._workflows:
            self._workflow.addItem(wf.metadata.workflow_id)

        stats = self._vm.stats()
        cloud = str(stats.cloud_count) if stats.cloud_available else "离线"
        self._summary.setText(f"模板版本：本地 {stats.local_count} · 云端 {cloud} · 失败 {stats.failed_count}")

        self._tree.clear()
        for record in self._vm.list_templates():
            QTreeWidgetItem(
                self._tree,
                [
                    record.identity.template_id,
                    record.identity.template_version,
                    record.status.value,
                    record.source,
                    record.instrument_profile,
                    record.error,
                ],
            )

    def _refresh_cloud(self) -> None:
        self._vm.refresh_cloud()
        self._reload()

    def _publish(self) -> None:
        idx = self._workflow.currentIndex()
        if idx < 0 or idx >= len(self._workflows):
            QMessageBox.warning(self, "无法发布", "请先在工作流设计页生成一个工作流")
            return
        workflow = self._workflows[idx].model_copy(deep=True)
        template_id = self._template_id.text().strip() or workflow.metadata.workflow_id
        version = self._version.text().strip()
        if not version:
            QMessageBox.warning(self, "缺少版本", "请输入 template_version。")
            return
        workflow.metadata.template_id = template_id
        workflow.metadata.template_version = version
        try:
            record = self._vm.publish(workflow)
        except Exception as exc:  # noqa: BLE001
            self._reload()
            QMessageBox.warning(self, "本地已保存，云端发布失败", str(exc))
            return
        self._reload()
        QMessageBox.information(self, "发布成功", f"已发布 {record.identity}")

    def _rollback(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        try:
            self._vm.rollback(item.text(0), item.text(1))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "回滚失败", str(exc))
            return
        self._reload()
