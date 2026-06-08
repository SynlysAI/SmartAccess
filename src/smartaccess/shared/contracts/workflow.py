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
