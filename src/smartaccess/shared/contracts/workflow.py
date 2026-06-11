"""Pydantic models for simplified `workflow.yaml`."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import ContractModel, FlexibleContractModel, NonEmptyStr

SIMPLIFIED_WORKFLOW_ACTIONS: tuple[str, ...] = ("click", "type", "hotkey", "press_enter")
LEGACY_WORKFLOW_ACTIONS: tuple[str, ...] = ("double_click", "wait", "wait_until", "screenshot_check")
MATCH_MODES: tuple[str, ...] = ("contains", "equals", "regex", "not_empty", "none")


class WorkflowMetadata(FlexibleContractModel):
    """Stable metadata for workflow drafts and published templates."""

    workflow_id: NonEmptyStr
    anchor_profile: NonEmptyStr | None = None
    instrument_profile: str | None = Field(default=None, exclude=True)
    author: NonEmptyStr
    lifecycle_state: NonEmptyStr
    experiment_type: str | None = None
    template_id: str | None = None
    template_version: str | None = None

    @model_validator(mode="after")
    def _normalize_profile(self) -> "WorkflowMetadata":
        if not self.anchor_profile and self.instrument_profile:
            self.anchor_profile = self.instrument_profile
        if not self.instrument_profile and self.anchor_profile:
            self.instrument_profile = self.anchor_profile
        if not self.anchor_profile:
            raise ValueError("anchor_profile is required")
        return self


class WorkflowStep(FlexibleContractModel):
    """A single linear workflow step bound to one anchor."""

    id: NonEmptyStr
    anchor_id: NonEmptyStr | None = None
    target: str | None = Field(default=None, exclude=True)
    action: Literal["click", "type", "hotkey", "press_enter"]
    value: Any | None = None
    condition: dict[str, Any] | None = Field(default=None, exclude=True)
    expected_text: str | None = None
    match_mode: Literal["contains", "equals", "regex", "not_empty", "none"] = "none"
    timeout_seconds: float | None = Field(default=None, ge=0)
    wait_seconds: float | None = Field(default=None, ge=0)
    requires_confirmation: bool = False
    migration_error: str | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _normalize_expectation(self) -> "WorkflowStep":
        if not self.anchor_id and self.target:
            self.anchor_id = self.target
        normalized = normalize_condition(self.condition)
        if normalized:
            if self.match_mode == "none" and normalized.get("match_mode"):
                self.match_mode = normalized["match_mode"]
            if self.expected_text is None and normalized.get("expected_text") is not None:
                self.expected_text = str(normalized["expected_text"])
            if self.timeout_seconds is None and normalized.get("timeout_seconds") is not None:
                self.timeout_seconds = float(normalized["timeout_seconds"])
        if self.match_mode == "none":
            self.expected_text = None
            self.timeout_seconds = None
        if not self.anchor_id:
            raise ValueError("anchor_id is required")
        return self


class WorkflowMigrationError(FlexibleContractModel):
    """A legacy step that could not be safely converted to the simplified model."""

    id: NonEmptyStr
    action: str
    target: str | None = None
    anchor_id: str | None = None
    reason: NonEmptyStr
    original: dict[str, Any] = Field(default_factory=dict)


class WorkflowOutput(FlexibleContractModel):
    """Legacy compatibility shape kept for older desktop/tests."""

    key: NonEmptyStr
    source: NonEmptyStr


class WorkflowRetryPolicy(FlexibleContractModel):
    """Legacy compatibility shape kept for older desktop/tests."""

    max_attempts: int = Field(default=1, ge=0)


class WorkflowContract(ContractModel):
    """Top-level contract for SmartAccess v2 workflows."""

    metadata: WorkflowMetadata
    steps: list[WorkflowStep] = Field(default_factory=list)
    roi_bindings: dict[str, str] = Field(default_factory=dict)
    outputs: list[WorkflowOutput] = Field(default_factory=list)
    retry_policy: WorkflowRetryPolicy = Field(default_factory=WorkflowRetryPolicy)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    migration_errors: list[WorkflowMigrationError] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_steps(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)
        steps, migration_errors = normalize_workflow_steps(data.get("steps") or [])
        data["steps"] = steps
        existing_errors = data.get("migration_errors") or []
        data["migration_errors"] = [*existing_errors, *migration_errors]
        return data

    @model_validator(mode="after")
    def _unique_step_ids(self) -> "WorkflowContract":
        step_ids = [step.id for step in self.steps]
        duplicates = sorted({step_id for step_id in step_ids if step_ids.count(step_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate step ids: {', '.join(duplicates)}")
        return self


def normalize_condition(condition: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert legacy source/mode/operator conditions to OCR expectation fields."""

    if not condition:
        return None
    operator = condition.get("match_mode") or condition.get("operator") or "contains"
    if operator == "exists":
        operator = "not_empty"
    if operator not in MATCH_MODES:
        operator = "contains"
    expected = condition.get("expected_text")
    if expected is None:
        expected = condition.get("expected")
    timeout = condition.get("timeout_seconds", condition.get("timeout"))
    normalized: dict[str, Any] = {"match_mode": operator}
    if expected is not None and operator != "not_empty":
        normalized["expected_text"] = str(expected)
    if timeout is not None:
        normalized["timeout_seconds"] = _coerce_seconds(timeout)
    return normalized


def normalize_workflow_steps(
    raw_steps: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return simplified steps plus standardized migration errors."""

    steps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="json", exclude_none=True)
        if not isinstance(raw, dict):
            errors.append(
                {
                    "id": f"legacy_step_{index + 1}",
                    "action": "unknown",
                    "reason": "legacy step is not an object; rebind to an action anchor",
                    "original": {"value": raw},
                }
            )
            continue
        step = dict(raw)
        action = str(step.get("action") or "").strip()
        step_id = str(step.get("id") or f"step_{index + 1}")
        if "anchor_id" not in step and step.get("target"):
            step["anchor_id"] = step.get("target")
        if action == "double_click":
            first = _action_step(step, action="click", step_id=f"{step_id}_click_1")
            second = _action_step(step, action="click", step_id=f"{step_id}_click_2")
            first.pop("expected_text", None)
            first.pop("timeout_seconds", None)
            first["match_mode"] = "none"
            steps.extend([first, second])
            continue
        if action in {"wait_until", "screenshot_check"}:
            condition = normalize_condition(step.get("condition"))
            if condition is None:
                condition = _condition_from_flat_step(step)
            if steps and condition:
                _merge_condition_into_step(steps[-1], condition)
            else:
                errors.append(_migration_error(step, "legacy OCR wait/check must follow an executable action step; rebind to an action anchor"))
            continue
        if action == "wait":
            wait_seconds = step.get("wait_seconds", step.get("value"))
            if steps and wait_seconds is not None:
                steps[-1]["wait_seconds"] = _coerce_seconds(wait_seconds)
            else:
                errors.append(_migration_error(step, "legacy fixed wait must follow an executable action step"))
            continue
        if action not in SIMPLIFIED_WORKFLOW_ACTIONS:
            errors.append(_migration_error(step, f"legacy action '{action or 'unknown'}' must be rebound to an action anchor"))
            continue
        clean = _action_step(step, action=action, step_id=step_id)
        flat_condition = _condition_from_flat_step(step)
        if flat_condition:
            _merge_condition_into_step(clean, flat_condition)
        steps.append(clean)
    return steps, errors


def _action_step(raw: dict[str, Any], *, action: str, step_id: str) -> dict[str, Any]:
    clean = dict(raw)
    clean["id"] = step_id
    clean["action"] = action
    if "anchor_id" not in clean and clean.get("target"):
        clean["anchor_id"] = clean.get("target")
    clean.pop("target", None)
    clean.pop("condition", None)
    clean.pop("migration_error", None)
    return clean


def _condition_from_flat_step(step: dict[str, Any]) -> dict[str, Any] | None:
    match_mode = step.get("match_mode")
    expected_text = step.get("expected_text")
    timeout = step.get("timeout_seconds")
    if match_mode in MATCH_MODES and (match_mode != "none" or expected_text is not None):
        condition: dict[str, Any] = {"match_mode": match_mode}
        if expected_text is not None:
            condition["expected_text"] = expected_text
        if timeout is not None:
            condition["timeout_seconds"] = timeout
        return condition
    return normalize_condition(step.get("condition"))


def _merge_condition_into_step(step: dict[str, Any], condition: dict[str, Any]) -> None:
    match_mode = condition.get("match_mode")
    if match_mode:
        step["match_mode"] = match_mode
    if condition.get("expected_text") is not None:
        step["expected_text"] = condition["expected_text"]
    if condition.get("timeout_seconds") is not None:
        step["timeout_seconds"] = condition["timeout_seconds"]


def _migration_error(step: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "id": str(step.get("id") or "legacy_step"),
        "action": str(step.get("action") or "unknown"),
        "target": step.get("target"),
        "anchor_id": step.get("anchor_id"),
        "reason": reason,
        "original": dict(step),
    }


def _coerce_seconds(value: Any) -> float:
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped.endswith("ms"):
            return float(stripped[:-2].strip()) / 1000.0
        if stripped.endswith("s"):
            return float(stripped[:-1].strip())
        value = stripped
    seconds = float(value)
    if seconds >= 1000:
        return seconds / 1000.0
    return seconds
