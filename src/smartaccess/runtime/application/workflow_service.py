"""工作流草稿、保存和标准化校验服务。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smartaccess.runtime.application.anchor_service import AnchorService
from smartaccess.runtime.application.ports import (
    WorkflowDraftGenerator,
    WorkflowListEntry,
)
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.validation import validate_workflow_against_anchors
from smartaccess.shared.contracts.workflow import WorkflowContract
from smartaccess.shared.logging import get_logger


class StandardizationResult:
    """工作流标准化预检查结果。"""

    def __init__(self, ok: bool, issues: list[str]) -> None:
        """初始化标准化结果。

        Args:
            ok: 是否通过。
            issues: 问题列表。
        """

        self.ok = ok
        self.issues = issues


@dataclass(frozen=True, slots=True)
class WorkflowDraftRecord:
    """工作流草稿生成记录。"""

    workflow_id: str
    prompt: str
    context: dict[str, Any]
    reasoning: str


class WorkflowService:
    """管理工作区下的工作流草稿和模板工作流索引。"""

    def __init__(
        self,
        *,
        workspace_dir: Path,
        anchors: AnchorService,
        draft_generator: WorkflowDraftGenerator | None = None,
    ) -> None:
        """初始化工作流服务。

        Args:
            workspace_dir: 工作区目录。
            anchors: 锚点服务。
            draft_generator: 可选 AI 草稿生成器。
        """

        self._workspace_dir = Path(workspace_dir)
        self._anchors = anchors
        self._draft_generator = draft_generator
        self._workflows: dict[str, WorkflowContract] = {}
        self._draft_records: dict[str, WorkflowDraftRecord] = {}
        self._logger = get_logger()
        self.load_all()

    def load_all(self) -> None:
        """加载全部工作流草稿和本地模板工作流。"""

        self._workflows.clear()
        paths = list((self._workspace_dir / "workflows").glob("*/draft.yaml"))
        paths.extend((self._workspace_dir / "templates").glob("*/*/workflow.yaml"))
        loaded_count = 0
        for path in sorted(paths):
            try:
                self.load(path)
                loaded_count += 1
            except Exception:  # noqa: BLE001 - 单个坏文件不能阻断启动
                self._logger.exception("工作流加载失败: %s", path)
        if loaded_count:
            self._logger.info("已加载 %d 个工作流", loaded_count)

    def draft_from_prompt(
        self,
        prompt: str,
        context: dict[str, Any],
    ) -> WorkflowContract:
        """调用草稿生成器创建工作流。

        Args:
            prompt: 用户提示词。
            context: 生成上下文。

        Returns:
            生成并保存后的工作流。
        """

        if self._draft_generator is None:
            raise RuntimeError("No WorkflowDraftGenerator configured")
        normalized_context = dict(context)
        if "anchor_profile" not in normalized_context and "instrument_profile" in context:
            normalized_context["anchor_profile"] = context["instrument_profile"]
        self._logger.info("AI 生成工作流中... prompt=%.100s", prompt)
        workflow = self._draft_generator.draft_from_prompt(prompt, normalized_context)
        self._logger.info("AI 工作流生成完成: workflow_id=%s, 步骤数=%d",
                          workflow.metadata.workflow_id, len(workflow.steps))
        reasoning = getattr(self._draft_generator, "last_reasoning", "") or ""
        self._draft_records[workflow.metadata.workflow_id] = WorkflowDraftRecord(
            workflow_id=workflow.metadata.workflow_id,
            prompt=prompt,
            context=normalized_context,
            reasoning=reasoning,
        )
        return self.register(workflow)

    def last_reasoning(self) -> str:
        """返回最近一次 AI 草稿推理文本。"""

        return getattr(self._draft_generator, "last_reasoning", "") or ""

    def generator_label(self) -> str:
        """返回草稿生成器标签。"""

        if self._draft_generator is None:
            return "未配置"
        label = getattr(self._draft_generator, "generator_label", None)
        if callable(label):
            return str(label())
        return type(self._draft_generator).__name__

    def register(self, workflow: WorkflowContract) -> WorkflowContract:
        """注册并保存工作流。"""

        normalized = WorkflowContract.model_validate(
            workflow.model_dump(mode="json", exclude_none=True)
        )
        self._workflows[normalized.metadata.workflow_id] = normalized
        self.save(normalized)
        self._logger.info("工作流已注册: workflow_id=%s, 步骤数=%d",
                          normalized.metadata.workflow_id, len(normalized.steps))
        return normalized

    def update(self, workflow: WorkflowContract) -> WorkflowContract:
        """更新工作流。"""

        return self.register(workflow)

    def load(self, path: str | Path) -> WorkflowContract:
        """从文件加载工作流。"""

        workflow = load_yaml_contract(path, WorkflowContract)
        self._workflows[workflow.metadata.workflow_id] = workflow
        return workflow

    def save(self, workflow: WorkflowContract) -> Path:
        """保存工作流草稿。"""

        normalized = WorkflowContract.model_validate(
            workflow.model_dump(mode="json", exclude_none=True)
        )
        return dump_yaml_contract(
            normalized,
            self._draft_path(normalized.metadata.workflow_id),
        )

    def get(self, workflow_id: str) -> WorkflowContract | None:
        """读取指定工作流。"""

        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[WorkflowContract]:
        """列出工作流。"""

        return list(self._workflows.values())

    def list_workflows_projected(self) -> list[WorkflowListEntry]:
        """列出 UI 使用的工作流投影。"""

        entries: list[WorkflowListEntry] = []
        for workflow in self._workflows.values():
            workflow_id = workflow.metadata.workflow_id
            draft_path = self._draft_path(workflow_id)
            if draft_path.exists():
                entries.append(
                    WorkflowListEntry(
                        workflow=workflow,
                        source_kind="draft",
                        storage_ref=str(draft_path),
                        display_label=f"{workflow_id} / Draft",
                    )
                )
            elif workflow.metadata.template_id and workflow.metadata.template_version:
                entries.append(
                    WorkflowListEntry(
                        workflow=workflow,
                        source_kind="local_template",
                        storage_ref=(
                            f"{workflow.metadata.template_id}@"
                            f"{workflow.metadata.template_version}"
                        ),
                        display_label=f"{workflow_id} / Local template",
                    )
                )
        return entries

    def delete_workflow(self, workflow_id: str) -> None:
        """删除工作流草稿。"""

        self._workflows.pop(workflow_id, None)
        self._draft_records.pop(workflow_id, None)
        draft_path = self._draft_path(workflow_id)
        if draft_path.exists():
            shutil.rmtree(draft_path.parent)
        self._logger.info("工作流已删除: workflow_id=%s", workflow_id)

    def draft_record(self, workflow_id: str) -> WorkflowDraftRecord | None:
        """读取工作流草稿生成记录。"""

        return self._draft_records.get(workflow_id)

    def standardize_check(self, workflow: WorkflowContract) -> StandardizationResult:
        """执行工作流标准化校验。"""

        migration_issues = [
            f"step {error.id}: {error.reason}"
            for error in getattr(workflow, "migration_errors", [])
        ]
        anchors = self._anchors.get_profile(workflow.metadata.anchor_profile)
        if anchors is None:
            issues = list(migration_issues)
            if not workflow.steps:
                issues.append("workflow.steps must not be empty")
            if not issues:
                issues.append(f"anchor profile not found: {workflow.metadata.anchor_profile}")
            return StandardizationResult(ok=not issues, issues=issues)
        issues = migration_issues + validate_workflow_against_anchors(workflow, anchors)
        return StandardizationResult(ok=not issues, issues=issues)

    def _draft_path(self, workflow_id: str) -> Path:
        """返回工作流草稿路径。"""

        return self._workspace_dir / "workflows" / workflow_id / "draft.yaml"
