"""Pydantic models for `run_trace.jsonl`."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import ContractModel, FlexibleContractModel, NonEmptyStr


class ObservationPayload(FlexibleContractModel):
    """Structured observation data emitted by the observer."""


class ActionPayload(FlexibleContractModel):
    """Action or recovery command written into the run trace."""

    type: NonEmptyStr
    target: str | None = None


class ResultPayload(FlexibleContractModel):
    """Execution result for a step or recovery action."""

    status: NonEmptyStr


class ArtifactPayload(FlexibleContractModel):
    """Artifact references such as screenshots and logs."""


class RunTraceRecord(ContractModel):
    """A single JSONL event inside `run_trace.jsonl`."""

    timestamp: datetime
    session_id: NonEmptyStr
    step_id: NonEmptyStr
    observation: ObservationPayload = Field(default_factory=ObservationPayload)
    action: ActionPayload
    result: ResultPayload
    artifacts: ArtifactPayload = Field(default_factory=ArtifactPayload)
