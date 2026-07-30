"""工作流设计视图模型。"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from smartaccess.runtime.application.workflow_service import StandardizationResult
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.workflow import WorkflowContract

from .base import ViewModel


class WorkflowViewModel(ViewModel):
    """工作流页和运行时门面之间的适配层。"""

    changed = pyqtSignal()

    def list_workflows(self) -> list[WorkflowContract]:
        """列出全部工作流。"""

        return self._facade.list_workflows()

    def list_anchor_profiles(self) -> list[AnchorsContract]:
        """列出全部锚点配置。"""

        return self._facade.list_instruments()

    def get_anchor_profile(self, profile_id: str | None) -> AnchorsContract | None:
        """读取指定锚点配置。"""

        return self._facade.get_instrument(profile_id) if profile_id else None

    def save_workflow(self, workflow: WorkflowContract) -> WorkflowContract:
        """保存工作流。"""

        saved = self._facade.save_workflow(workflow)
        self.changed.emit()
        return saved

    def draft_workflow(
        self,
        prompt: str,
        context: dict,
    ) -> WorkflowContract:
        """调用 AI 生成工作流草稿。

        Args:
            prompt: 用户描述。
            context: 生成上下文。

        Returns:
            工作流草稿。
        """

        workflow = self._facade.draft_workflow_from_prompt(prompt, context)
        self.changed.emit()
        return workflow

    def ai_label(self) -> str:
        """返回当前 AI 生成器标签。"""

        return self._facade.workflow_ai_label()

    def ai_reasoning(self) -> str:
        """返回最近一次 AI 生成摘要。"""

        return self._facade.workflow_ai_reasoning()

    def delete_workflow(self, workflow_id: str) -> None:
        """删除工作流。"""

        self._facade.delete_workflow(workflow_id)
        self.changed.emit()

    def standardize(self, workflow: WorkflowContract) -> StandardizationResult:
        """执行标准化检查。"""

        return self._facade.standardize(workflow)

    def preview_increment_value(self, workflow_id: str, rule: dict) -> int:
        """Return the next persisted increment value for preview."""

        return self._facade.preview_increment_value(workflow_id, rule)
