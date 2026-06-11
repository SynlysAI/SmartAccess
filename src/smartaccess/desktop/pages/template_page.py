"""Template library page: list versions, publish standard templates, roll back."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from smartaccess.desktop.shell import theme as t
from smartaccess.desktop.viewmodels.template_vm import TemplateViewModel
from smartaccess.desktop.widgets.cards import Card, hint_label, page_header, section_title

_STATUS_COLOR = {
    "published": t.SUCCESS,
    "draft": t.INK_SUBTLE,
    "superseded": t.INK_SUBTLE,
    "rolled_back": t.WARNING,
    "rolledback": t.WARNING,
}


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
        self._summary.setObjectName("Body")
        refresh_cloud = QPushButton("刷新云端")
        refresh_cloud.setObjectName("Ghost")
        refresh_cloud.clicked.connect(self._refresh_cloud)
        summary.addWidget(self._summary)
        summary.addStretch(1)
        summary.addWidget(refresh_cloud)
        root.addLayout(summary)

        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("查找模板 ID、版本、anchor_profile、来源或错误")
        self._search.textChanged.connect(self._reload_versions)
        self._status_filter = QComboBox()
        self._status_filter.addItems(["All", "Published", "Draft", "Superseded", "RolledBack", "Standardized"])
        self._status_filter.currentTextChanged.connect(self._reload_versions)
        filters.addWidget(QLabel("查找"))
        filters.addWidget(self._search, 1)
        filters.addWidget(QLabel("状态"))
        filters.addWidget(self._status_filter)
        root.addLayout(filters)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_publish_card(), 2)
        body.addWidget(self._build_versions_card(), 3)
        root.addLayout(body, 1)

        self._reload()

    def on_show(self) -> None:
        self._reload()

    def _build_publish_card(self) -> QWidget:
        left = Card()
        left.add(section_title("发布标准模板"))
        left.add(
            hint_label("把一个已设计好的工作流固化为可复用的「标准模板」并发布到 SpecLabOS "
                       "模板中心。下面三项决定模板在模板中心里的身份与版本。")
        )
        form = QFormLayout()
        form.setSpacing(8)

        self._workflow = QComboBox()
        self._workflow.setToolTip("选择要发布的源工作流；其步骤与绑定会被打包成模板。")
        form.addRow("源工作流", self._workflow)

        self._template_id = QLineEdit()
        self._template_id.setPlaceholderText("例如 battery_cycle_standard")
        self._template_id.setToolTip(
            "模板的稳定标识，跨版本不变。它是别人在模板中心检索、复用这套流程的名字。"
            "留空时自动使用源工作流的 ID。"
        )
        form.addRow("模板 ID", self._template_id)

        self._version = QLineEdit()
        self._version.setPlaceholderText("例如 1.0.0（语义化版本）")
        self._version.setToolTip(
            "本次发布的版本号。同一模板 ID 可有多个版本，发布新版本会把旧版本标记为 superseded，"
            "需要时可回滚到任一历史版本。"
        )
        form.addRow("模板版本", self._version)
        left.body().addLayout(form)

        publish = QPushButton("发布到 SpecLabOS 模板中心")
        publish.clicked.connect(self._publish)
        left.add(publish)
        left.add(
            hint_label("提示：发布会先在本地保存一份可执行副本，再尝试推送云端；"
                       "云端不可达时本地副本依旧可用，稍后可重试。")
        )
        left.body().addStretch(1)
        return left

    def _build_versions_card(self) -> QWidget:
        right = Card()
        right.add(section_title("模板版本"))
        right.add(
            hint_label("当前回滚支持在已加载版本间切换当前发布版本；它不是完整文件历史恢复。"
                       "需要恢复内容时，请选择历史版本后重新发布或另存为新版本。")
        )
        self._tree = QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(["模板 ID", "版本", "状态", "来源", "anchor_profile", "错误"])
        self._tree.setRootIsDecorated(False)
        self._tree.itemSelectionChanged.connect(self._update_timeline)
        right.add(self._tree)
        self._timeline = QTextBrowser()
        self._timeline.setObjectName("LogView")
        self._timeline.setMinimumHeight(150)
        self._timeline.setMarkdown("_选择一个版本查看时间线。_")
        right.add(self._timeline)
        actions = QHBoxLayout()
        rollback = QPushButton("回滚到所选版本")
        rollback.setObjectName("Ghost")
        rollback.clicked.connect(self._rollback)
        update = QPushButton("更新仪器")
        update.setObjectName("Ghost")
        update.clicked.connect(self._update_selected)
        delete = QPushButton("删除版本")
        delete.setObjectName("Ghost")
        delete.clicked.connect(self._delete_selected)
        actions.addWidget(rollback)
        actions.addWidget(update)
        actions.addWidget(delete)
        actions.addStretch(1)
        right.body().addLayout(actions)
        return right

    def _reload(self) -> None:
        self._workflow.clear()
        self._workflows = self._vm.publishable_workflows()
        for wf in self._workflows:
            self._workflow.addItem(wf.metadata.workflow_id)

        stats = self._vm.stats()
        cloud = str(stats.cloud_count) if stats.cloud_available else "离线"
        self._summary.setText(
            f"模板版本：本地 {stats.local_count} · 云端 {cloud} · 失败 {stats.failed_count}"
        )

        self._reload_versions()

    def _reload_versions(self) -> None:
        self._tree.clear()
        query = self._search.text() if hasattr(self, "_search") else ""
        status = self._status_filter.currentText() if hasattr(self, "_status_filter") else "All"
        for record in self._vm.search_templates(query, status):
            item = QTreeWidgetItem(
                self._tree,
                [
                    record.identity.template_id,
                    record.identity.template_version,
                    record.status.value,
                    record.source,
                    record.anchor_profile,
                    record.error,
                ],
            )
            color = _STATUS_COLOR.get(record.status.value.lower().replace("_", ""))
            if color:
                item.setForeground(2, QColor(color))
            if record.error:
                item.setForeground(5, QColor(t.DANGER))
        self._update_timeline()

    def _update_timeline(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            self._timeline.setMarkdown("_选择一个版本查看时间线。_")
            return
        template_id = item.text(0)
        selected_version = item.text(1)
        records = [r for r in self._vm.list_templates() if r.identity.template_id == template_id]
        records.sort(key=lambda r: r.published_at or r.identity.template_version, reverse=True)
        lines = [f"**{template_id} 版本时间线**", ""]
        for record in records:
            marker = "●" if record.identity.template_version == selected_version else "○"
            published = record.published_at or "本地加载"
            lines.append(
                f"{marker} `{record.identity.template_version}` · {record.status.value} · "
                f"{published} · {record.source} · {record.anchor_profile or '-'}"
            )
            if record.error:
                lines.append(f"  错误: {record.error}")
        self._timeline.setMarkdown("\n".join(lines))

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
            QMessageBox.warning(self, "缺少版本", "请输入模板版本，例如 1.0.0。")
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

    def _update_selected(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        anchor_profile = item.text(4).strip()
        value, ok = QInputDialog.getText(
            self, "更新版本", "anchor_profile", text=anchor_profile
        )
        if not ok:
            return
        try:
            self._vm.update_version(
                item.text(0), item.text(1), anchor_profile=value.strip()
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "更新失败", str(exc))
            return
        self._reload()

    def _delete_selected(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        template_id = item.text(0)
        template_version = item.text(1)
        status = item.text(2)
        force = status == "Published"
        warning = "\n当前版本仍是 Published，将会强制删除。" if force else ""
        answer = QMessageBox.question(
            self,
            "确认删除",
            f"将删除模板版本 {template_id}@{template_version}。{warning}\n"
            "此操作会移除本地版本记录和 workflow.yaml，且不可撤销。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._vm.delete_version(template_id, template_version, force=force)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self._reload()
