"""模板与平台页面视图模型。"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from smartaccess.desktop.viewmodels.base import ViewModel
from smartaccess.runtime.application.template_service import TemplateRecord
from smartaccess.shared.contracts.workflow import WorkflowContract


DEFAULT_TEMPLATE_VERSION = "1.0.0"


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

    def template_exists(self, template_id: str, template_version: str) -> bool:
        """判断模板版本是否已存在。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。

        Returns:
            模板版本存在时返回 True。
        """

        return any(
            record.identity.template_id == template_id
            and record.identity.template_version == template_version
            for record in self._facade.list_templates()
        )

    def next_template_version(self, template_id: str) -> str:
        """生成指定模板的下一个版本号。

        Args:
            template_id: 模板 ID。

        Returns:
            下一个可用模板版本。
        """

        versions = [
            record.identity.template_version
            for record in self._facade.list_templates()
            if record.identity.template_id == template_id
        ]
        semantic_versions = [
            tuple(int(part) for part in version.split("."))
            for version in versions
            if self._is_semantic_version(version)
        ]
        if semantic_versions:
            major, minor, patch = max(semantic_versions)
            return f"{major}.{minor}.{patch + 1}"
        numeric_versions = [int(version) for version in versions if version.isdigit()]
        if numeric_versions:
            return str(max(numeric_versions) + 1)
        return DEFAULT_TEMPLATE_VERSION

    @staticmethod
    def _is_semantic_version(version: str) -> bool:
        """判断版本号是否为三段数字语义版本。

        Args:
            version: 模板版本号。

        Returns:
            符合 x.y.z 格式时返回 True。
        """

        parts = version.split(".")
        return len(parts) == 3 and all(part.isdigit() for part in parts)

    def publish(
        self,
        workflow_id: str,
        *,
        template_id: str | None = None,
        template_version: str = DEFAULT_TEMPLATE_VERSION,
    ) -> TemplateRecord:
        """发布指定工作流。

        Args:
            workflow_id: 工作流 ID。
            template_id: 模板 ID；为空时使用工作流 ID。
            template_version: 模板版本。

        Returns:
            模板记录。
        """

        workflow = self._facade.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"工作流不存在: {workflow_id}")
        workflow = WorkflowContract.model_validate(
            workflow.model_dump(mode="json", exclude_none=True)
        )
        workflow.metadata.template_id = template_id or workflow_id
        workflow.metadata.template_version = template_version
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

    def delete_cloud_first(
        self,
        template_id: str,
        template_version: str,
        *,
        force: bool,
    ) -> None:
        """先删除云端模板，再删除本地副本。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
            force: 是否强制删除。
        """

        self._facade.delete_template_version_cloud_first(
            template_id,
            template_version,
            force=force,
        )
        self.changed.emit()

    def instruments(self) -> list[str]:
        """列出可关联的设备锚点配置 ID。"""

        return [profile.profile_id for profile in self._facade.list_instruments()]

