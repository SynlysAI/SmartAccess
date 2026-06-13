"""模板与平台页面视图模型。"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from smartaccess_v2.desktop.viewmodels.base import ViewModel
from smartaccess_v2.runtime.application.template_service import TemplateRecord
from smartaccess_v2.shared.contracts.workflow import WorkflowContract


class TemplateViewModel(ViewModel):
    """模板页和运行时门面之间的适配层。"""

    changed = pyqtSignal()

    def workflows(self) -> list[WorkflowContract]:
        """列出可发布工作流。"""

        return self._facade.list_workflows()

    def templates(
        self,
        query: str = "",
        status: str = "",
    ) -> list[TemplateRecord]:
        """搜索模板记录。

        Args:
            query: 搜索关键字。
            status: 状态过滤。

        Returns:
            模板记录列表。
        """

        return self._facade.search_templates(query=query, status=status)

    def publish(self, workflow_id: str) -> TemplateRecord:
        """发布指定工作流。

        Args:
            workflow_id: 工作流 ID。

        Returns:
            模板记录。
        """

        workflow = self._facade.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")
        record = self._facade.publish_template(workflow)
        self.changed.emit()
        return record

    def refresh_cloud(self) -> None:
        """刷新云端模板索引。"""

        self._facade.refresh_cloud_templates()
        self.changed.emit()

    def delete(self, template_id: str, template_version: str, *, force: bool) -> None:
        """删除模板版本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            force: 是否强制删除。
        """

        self._facade.delete_template_version(
            template_id,
            template_version,
            force=force,
        )
        self.changed.emit()

    def update_anchor_profile(
        self,
        template_id: str,
        template_version: str,
        anchor_profile: str,
    ) -> TemplateRecord:
        """更新模板版本关联的设备锚点配置。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            anchor_profile: 设备锚点配置 ID。

        Returns:
            更新后的模板记录。
        """

        record = self._facade.update_template_version(
            template_id,
            template_version,
            anchor_profile=anchor_profile,
        )
        self.changed.emit()
        return record

    def rollback(self, template_id: str, template_version: str) -> TemplateRecord:
        """回滚到指定模板版本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            回滚后的模板记录。
        """

        record = self._facade.rollback_template(template_id, template_version)
        self.changed.emit()
        return record

    def instruments(self) -> list[str]:
        """列出可关联的设备锚点配置 ID。"""

        return [profile.profile_id for profile in self._facade.list_instruments()]

    def sync_outbox(self) -> None:
        """同步平台 outbox。"""

        self._facade.sync_platform_outbox()
        self.changed.emit()
