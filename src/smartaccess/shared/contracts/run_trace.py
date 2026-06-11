"""Pydantic models for `run_trace.jsonl`."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, FlexibleContractModel, NonEmptyStr


class ActionPayload(FlexibleContractModel):
    """Action command written into the run trace."""

    type: NonEmptyStr
    value: Any | None = None


class WaitStrategyPayload(FlexibleContractModel):
    """How the runner waited after an action."""

    type: Literal["ocr_poll", "fixed_wait"]
    wait_seconds: float | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, ge=0)
    poll_interval_seconds: float | None = Field(default=None, ge=0)


class ErrorPayload(FlexibleContractModel):
    """Optional step error details."""

    type: str | None = None
    message: str | None = None
    detail: Any | None = None


class RunTraceRecord(ContractModel):
    """A single step-level JSONL fact inside `run_trace.jsonl`."""

    timestamp: datetime
    session_id: NonEmptyStr
    workflow_id: NonEmptyStr
    step_id: NonEmptyStr
    anchor_id: NonEmptyStr
    action: ActionPayload
    wait_strategy: WaitStrategyPayload
    expected_text: str | None = None
    actual_text: str | None = None
    match_mode: Literal["contains", "equals", "regex", "not_empty", "none"] = "none"
    matched: bool | None = None
    attempts: int = Field(default=1, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0)
    screenshot_path: str | None = None
    status: Literal["success", "timeout", "failed", "cancelled"]
    error: ErrorPayload | None = None
    provider_mode: str | None = None
    template_id: str | None = None
    template_version: str | None = None
