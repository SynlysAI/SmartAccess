"""WorkflowService: draft, bind, standardize, and persist workflows.

Binds the ``workflow.yaml`` contract to the use-case layer: generates drafts
from a natural-language prompt (via the :class:`WorkflowDraftGenerator` port),
runs standardization checks, persists drafts under the workspace, and advances
the workflow lifecycle.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smartaccess.runtime.application.ports import WorkflowDraftGenerator, WorkflowListEntry
from smartaccess.runtime.domain.workflow import WorkflowLifecycleState, can_transition
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.workflow import WorkflowContract


class StandardizationResult:
    """Outcome of a standardization pre-check."""

    def __init__(self, ok: bool, issues: list[str]) -> None:
        self.ok = ok
        self.issues = issues


@dataclass(frozen=True, slots=True)
class WorkflowDraftRecord:
    """Ephemeral UI-facing record of how a draft was generated."""

    workflow_id: str
    prompt: str
    context: dict[str, Any]
    reasoning: str


class WorkflowService:
    """Owns workflow drafts/templates and lifecycle helpers."""

    def __init__(
        self,
        *,
        draft_generator: WorkflowDraftGenerator | None = None,
        workspace_dir: Path,
        ai_store: Any = None,
    ) -> None:
        self._draft_generator = draft_generator
        self._workspace_dir = Path(workspace_dir)
        self._ai_store = ai_store
        self._workflows: dict[str, WorkflowContract] = {}
        self._draft_records: dict[str, WorkflowDraftRecord] = {}
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

        # 1. Search approved knowledge
        memory_hits: list[dict] = []
        skill_hits: list[dict] = []
        knowledge_hit_ids: list[str] = []
        if self._ai_store is not None:
            memory_hits = self._ai_store.search_memories(prompt, context)
            skill_hits = self._ai_store.search_skills(prompt, context)
            if memory_hits or skill_hits:
                context["_knowledge_hits"] = memory_hits + skill_hits
                knowledge_hit_ids = self._ai_store.get_hits_for_reasoning(memory_hits, skill_hits)

        # 2. Generate
        workflow = self._draft_generator.draft_from_prompt(prompt, context)

        # 3. Build reasoning with knowledge hits
        reasoning = getattr(self._draft_generator, "last_reasoning", "") or ""
        if knowledge_hit_ids:
            reasoning = "\n".join(knowledge_hit_ids) + "\n\n---\n\n" + reasoning

        self._draft_records[workflow.metadata.workflow_id] = WorkflowDraftRecord(
            workflow_id=workflow.metadata.workflow_id,
            prompt=prompt,
            context=dict(context),
            reasoning=reasoning,
        )
        self.register(workflow)

        # 4. Extract candidates for future runs
        if self._ai_store is not None:
            try:
                self._ai_store.extract_candidates(
                    workflow.model_dump(mode="json", exclude_none=True),
                    prompt=prompt,
                    reasoning=reasoning,
                )
                # Record episode
                self._ai_store.record_episode(
                    prompt=prompt,
                    workflow_id=workflow.metadata.workflow_id,
                    hit_memory_ids=[h["id"] for h in memory_hits],
                    hit_skill_ids=[h["id"] for h in skill_hits],
                    generation_result="success",
                )
            except Exception:
                pass  # Extraction errors should never block generation

        return workflow

    def last_reasoning(self) -> str:
        """The most recent generator's reasoning/analysis trace, if any."""

        return getattr(self._draft_generator, "last_reasoning", "") or ""

    def generator_label(self) -> str:
        """A short label of the active draft generator for the UI."""

        if self._draft_generator is None:
            return "未配置"
        name = type(self._draft_generator).__name__
        return "DeepSeek" if "DeepSeek" in name else "模板生成器"

    def register(self, workflow: WorkflowContract) -> WorkflowContract:
        self._workflows[workflow.metadata.workflow_id] = workflow
        self.save(workflow)
        return workflow

    def update(self, workflow: WorkflowContract) -> WorkflowContract:
        """Persist edits to an existing workflow draft."""

        return self.register(workflow)

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

    def list_workflows_projected(self) -> list[WorkflowListEntry]:
        """Return workflows with source-kind differentiation for the UI."""
        entries: list[WorkflowListEntry] = []
        for wf in self._workflows.values():
            wid = wf.metadata.workflow_id
            draft_path = self._draft_path(wid)
            if draft_path.exists():
                entries.append(WorkflowListEntry(
                    workflow=wf,
                    source_kind="draft",
                    storage_ref=str(draft_path),
                    display_label=f"📝 {wid} · Draft",
                ))
            elif wf.metadata.template_id and wf.metadata.template_version:
                entries.append(WorkflowListEntry(
                    workflow=wf,
                    source_kind="local_template",
                    storage_ref=f"{wf.metadata.template_id}@{wf.metadata.template_version}",
                    display_label=f"📋 {wid} · 本地模板",
                ))
            else:
                entries.append(WorkflowListEntry(
                    workflow=wf,
                    source_kind="draft",
                    storage_ref="",
                    display_label=f"📝 {wid} · Draft",
                ))
        return entries

    def delete_workflow(self, workflow_id: str) -> None:
        """Delete a workflow draft. Removes from memory and disk."""
        wf = self._workflows.pop(workflow_id, None)
        self._draft_records.pop(workflow_id, None)
        if wf is not None:
            draft_path = self._draft_path(workflow_id)
            if draft_path.exists():
                shutil.rmtree(draft_path.parent)

    def draft_record(self, workflow_id: str) -> WorkflowDraftRecord | None:
        return self._draft_records.get(workflow_id)

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
        # Validate wait_until and screenshot_check have conditions
        for step in workflow.steps:
            if step.action in {"wait_until", "screenshot_check"}:
                if not step.condition:
                    issues.append(f"步骤 {step.id} ({step.action}) 必须配置观测条件 (condition)")
                else:
                    cond = step.condition
                    if not cond.get("source"):
                        issues.append(f"步骤 {step.id} ({step.action}) 的 condition 缺少 source")
        # Warn about suspiciously large wait values
        for step in workflow.steps:
            if step.action == "wait" and step.value is not None:
                try:
                    val = float(str(step.value))
                    if 301 <= val <= 999:
                        issues.append(f"⚠ 步骤 {step.id} wait={val}s 超过 5 分钟，请人工确认是否为秒")
                except (ValueError, TypeError):
                    pass
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
