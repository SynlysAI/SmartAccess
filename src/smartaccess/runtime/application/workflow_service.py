"""WorkflowService: draft, bind, standardize, and persist workflows.

Binds the ``workflow.yaml`` contract to the use-case layer: generates drafts
from a natural-language prompt (via the :class:`WorkflowDraftGenerator` port),
runs standardization checks, persists drafts under the workspace, and advances
the workflow lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from smartaccess.runtime.application.ports import WorkflowDraftGenerator
from smartaccess.runtime.domain.workflow import WorkflowLifecycleState, can_transition
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.workflow import WorkflowContract


class StandardizationResult:
    """Outcome of a standardization pre-check."""

    def __init__(self, ok: bool, issues: list[str]) -> None:
        self.ok = ok
        self.issues = issues


class WorkflowService:
    """Owns workflow drafts/templates and lifecycle helpers."""

    def __init__(
        self,
        *,
        draft_generator: WorkflowDraftGenerator | None = None,
        workspace_dir: Path,
    ) -> None:
        self._draft_generator = draft_generator
        self._workspace_dir = Path(workspace_dir)
        self._workflows: dict[str, WorkflowContract] = {}
        self.load_all()

    def load_all(self) -> None:
        """Load saved workflow drafts and local template workflows from disk."""

        paths = list((self._workspace_dir / "workflows").glob("*/draft.yaml"))
        paths.extend((self._workspace_dir / "templates").glob("*/*/workflow.yaml"))
        for path in sorted(paths):
            try:
                self.load(path)
            except Exception:
                continue

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        if self._draft_generator is None:
            raise RuntimeError("未配置 WorkflowDraftGenerator，无法从自然语言生成草稿")
        workflow = self._draft_generator.draft_from_prompt(prompt, context)
        self.register(workflow)
        return workflow

    def register(self, workflow: WorkflowContract) -> WorkflowContract:
        self._workflows[workflow.metadata.workflow_id] = workflow
        self.save(workflow)
        return workflow

    def load(self, path: str | Path) -> WorkflowContract:
        workflow = load_yaml_contract(path, WorkflowContract)
        self._workflows[workflow.metadata.workflow_id] = workflow
        return workflow

    def save(self, workflow: WorkflowContract) -> Path:
        return dump_yaml_contract(workflow, self._draft_path(workflow.metadata.workflow_id))

    def get(self, workflow_id: str) -> WorkflowContract | None:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[WorkflowContract]:
        return list(self._workflows.values())

    def lifecycle_state(self, workflow: WorkflowContract) -> WorkflowLifecycleState:
        return WorkflowLifecycleState.from_contract(workflow.metadata.lifecycle_state)

    def standardize_check(self, workflow: WorkflowContract) -> StandardizationResult:
        """Verify a workflow satisfies the prerequisites to be Standardized."""

        issues: list[str] = []
        if not workflow.steps:
            issues.append("工作流缺少步骤")
        if not workflow.metadata.instrument_profile:
            issues.append("未绑定仪器画像")
        if not workflow.roi_bindings:
            issues.append("缺少 ROI 绑定")
        if not workflow.outputs:
            issues.append("未声明输出项")
        return StandardizationResult(ok=not issues, issues=issues)

    def transition(
        self, workflow: WorkflowContract, target: WorkflowLifecycleState
    ) -> WorkflowContract:
        """Move a workflow to ``target`` if the lifecycle guard allows it."""

        current = self.lifecycle_state(workflow)
        if not can_transition(current, target):
            raise ValueError(f"非法状态流转: {current} -> {target}")
        updated = workflow.model_copy(deep=True)
        updated.metadata.lifecycle_state = target.value
        self._workflows[updated.metadata.workflow_id] = updated
        self.save(updated)
        return updated

    def _draft_path(self, workflow_id: str) -> Path:
        return self._workspace_dir / "workflows" / workflow_id / "draft.yaml"
