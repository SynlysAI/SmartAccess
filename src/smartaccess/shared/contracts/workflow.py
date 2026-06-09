"""Pydantic models for `workflow.yaml`."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import ContractModel, FlexibleContractModel, JsonMap, NonEmptyStr


class WorkflowMetadata(FlexibleContractModel):
    """Stable metadata for workflow drafts and published templates."""

    workflow_id: NonEmptyStr
    template_id: str | None = None
    template_version: str | None = None
    author: NonEmptyStr
    instrument_profile: NonEmptyStr
    experiment_type: NonEmptyStr
    lifecycle_state: NonEmptyStr


class WorkflowPrecondition(FlexibleContractModel):
    """A single workflow precondition entry."""


class WorkflowStep(FlexibleContractModel):
    """A single workflow step driven by an action primitive."""

    id: NonEmptyStr
    action: NonEmptyStr
    target: str | None = None
    value: Any | None = None
    condition: JsonMap | None = None


class WorkflowOutput(FlexibleContractModel):
    """A single output binding declared by the workflow."""

    key: NonEmptyStr
    source: NonEmptyStr


class WorkflowRetryPolicy(FlexibleContractModel):
    """Global retry policy attached to a workflow."""

    max_attempts: int | None = Field(default=None, ge=0)


class WorkflowContract(ContractModel):
    """Top-level contract for SmartAccess workflows."""

    metadata: WorkflowMetadata
    preconditions: list[WorkflowPrecondition] = Field(default_factory=list)
    roi_bindings: dict[str, str] = Field(default_factory=dict)
    steps: list[WorkflowStep] = Field(default_factory=list)
    outputs: list[WorkflowOutput] = Field(default_factory=list)
    retry_policy: WorkflowRetryPolicy | None = None


# --------------------------------------------------------------------------- #
# Condition helpers — backward-compatible read of legacy fields
# --------------------------------------------------------------------------- #
def normalize_condition(condition: JsonMap | None) -> JsonMap | None:
    """Ensure condition uses standard second-based fields.

    Reads legacy ``timeout`` (milliseconds) and converts to ``timeout_seconds``.
    Returns a new dict; never mutates the input.
    """
    if not condition:
        return None
    normalized = dict(condition)
    # Backward-compat: old "timeout" (often in ms) → timeout_seconds
    if "timeout" in normalized and "timeout_seconds" not in normalized:
        legacy = normalized.pop("timeout")
        try:
            val = float(str(legacy))
        except (TypeError, ValueError):
            val = 0.0
        # If the value looks like milliseconds (>= 1000), convert to seconds
        if val >= 1000:
            normalized["timeout_seconds"] = val / 1000.0
            normalized.setdefault("_normalization_note", f"legacy timeout {val}ms → {val/1000:.1f}s")
        else:
            normalized["timeout_seconds"] = val
    # Ensure standard fields exist with defaults
    normalized.setdefault("source", "")
    normalized.setdefault("mode", "ocr")
    normalized.setdefault("operator", "exists")
    normalized.setdefault("expected", "")
    normalized.setdefault("timeout_seconds", 30.0)
    normalized.setdefault("poll_interval_seconds", 1.0)
    return normalized
