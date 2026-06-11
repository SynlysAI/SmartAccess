"""WorkflowService: draft, validate, persist, and transition workflows."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smartaccess.runtime.application.anchor_service import AnchorService
from smartaccess.runtime.application.ports import WorkflowDraftGenerator, WorkflowListEntry
from smartaccess.runtime.domain.workflow import WorkflowLifecycleState, can_transition
from smartaccess.shared.contracts import (
    WorkflowContract,
    dump_yaml_contract,
    load_yaml_contract,
    validate_workflow_against_anchors,
)


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
        self._anchors = AnchorService(workspace_dir=self._workspace_dir)
        self._workflows: dict[str, WorkflowContract] = {}
        self._draft_records: dict[str, WorkflowDraftRecord] = {}
        self.load_all()

    def load_all(self) -> None:
        paths = list((self._workspace_dir / "workflows").glob("*/draft.yaml"))
        paths.extend((self._workspace_dir / "templates").glob("*/*/workflow.yaml"))
        for path in sorted(paths):
            try:
                self.load(path)
            except Exception:
                continue

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> WorkflowContract:
        if self._draft_generator is None:
            raise RuntimeError("No WorkflowDraftGenerator configured")

        context = dict(context)
        if "anchor_profile" not in context and "instrument_profile" in context:
            context["anchor_profile"] = context["instrument_profile"]

        memory_hits: list[dict] = []
        skill_hits: list[dict] = []
        knowledge_hit_ids: list[str] = []
        if self._ai_store is not None:
            memory_hits = self._ai_store.search_memories(prompt, context)
            skill_hits = self._ai_store.search_skills(prompt, context)
            if memory_hits or skill_hits:
                context["_knowledge_hits"] = memory_hits + skill_hits
                knowledge_hit_ids = self._ai_store.get_hits_for_reasoning(memory_hits, skill_hits)

        workflow = self._draft_generator.draft_from_prompt(prompt, context)
        check = self.standardize_check(workflow)
        context["_generated_steps"] = [
            {
                "id": step.id,
                "anchor_id": step.anchor_id,
                "action": step.action,
                "match_mode": step.match_mode,
                "expected_text": step.expected_text,
            }
            for step in workflow.steps
        ]
        context["_standardization_ok"] = check.ok
        context["_standardization_issues"] = list(check.issues)
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
        return workflow

    def last_reasoning(self) -> str:
        return getattr(self._draft_generator, "last_reasoning", "") or ""

    def generator_label(self) -> str:
        if self._draft_generator is None:
            return "Not configured"
        label = getattr(self._draft_generator, "generator_label", None)
        if callable(label):
            return str(label())
        name = type(self._draft_generator).__name__
        return "DeepSeek" if "DeepSeek" in name else "Template"

    def register(self, workflow: WorkflowContract) -> WorkflowContract:
        normalized = WorkflowContract.model_validate(workflow.model_dump(mode="json", exclude_none=True))
        self._workflows[normalized.metadata.workflow_id] = normalized
        self.save(normalized)
        return normalized

    def update(self, workflow: WorkflowContract) -> WorkflowContract:
        return self.register(workflow)

    def load(self, path: str | Path) -> WorkflowContract:
        workflow = load_yaml_contract(path, WorkflowContract)
        self._workflows[workflow.metadata.workflow_id] = workflow
        return workflow

    def save(self, workflow: WorkflowContract) -> Path:
        normalized = WorkflowContract.model_validate(workflow.model_dump(mode="json", exclude_none=True))
        return dump_yaml_contract(normalized, self._draft_path(normalized.metadata.workflow_id))

    def get(self, workflow_id: str) -> WorkflowContract | None:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[WorkflowContract]:
        return list(self._workflows.values())

    def list_workflows_projected(self) -> list[WorkflowListEntry]:
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
                        storage_ref=f"{workflow.metadata.template_id}@{workflow.metadata.template_version}",
                        display_label=f"{workflow_id} / Local template",
                    )
                )
        return entries

    def delete_workflow(self, workflow_id: str) -> None:
        self._workflows.pop(workflow_id, None)
        self._draft_records.pop(workflow_id, None)
        draft_path = self._draft_path(workflow_id)
        if draft_path.exists():
            shutil.rmtree(draft_path.parent)

    def draft_record(self, workflow_id: str) -> WorkflowDraftRecord | None:
        return self._draft_records.get(workflow_id)

    def lifecycle_state(self, workflow: WorkflowContract) -> WorkflowLifecycleState:
        return WorkflowLifecycleState.from_contract(workflow.metadata.lifecycle_state)

    def standardize_check(self, workflow: WorkflowContract) -> StandardizationResult:
        migration_issues = [
            f"step {error.id}: {error.reason}"
            for error in getattr(workflow, "migration_errors", [])
        ]
        anchors = self._anchors.get_profile(workflow.metadata.anchor_profile)
        if anchors is None:
            issues = list(migration_issues)
            if not workflow.steps:
                issues.append("workflow.steps must not be empty")
            return StandardizationResult(ok=not issues, issues=issues)
        issues = migration_issues + validate_workflow_against_anchors(workflow, anchors)
        return StandardizationResult(ok=not issues, issues=issues)

    def transition(
        self,
        workflow: WorkflowContract,
        target: WorkflowLifecycleState,
    ) -> WorkflowContract:
        current = self.lifecycle_state(workflow)
        if not can_transition(current, target):
            raise ValueError(f"illegal workflow transition: {current} -> {target}")
        updated = workflow.model_copy(deep=True)
        updated.metadata.lifecycle_state = target.value
        self._workflows[updated.metadata.workflow_id] = updated
        self.save(updated)
        return updated

    def _draft_path(self, workflow_id: str) -> Path:
        return self._workspace_dir / "workflows" / workflow_id / "draft.yaml"
