"""run_trace.jsonl 的契约模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import ContractModel, FlexibleContractModel, NonEmptyStr


class ActionPayload(FlexibleContractModel):
    """写入运行轨迹的动作命令。"""

    type: NonEmptyStr
    value: Any | None = None


class WaitStrategyPayload(FlexibleContractModel):
    """步骤执行后的等待策略。"""

    type: Literal["ocr_poll", "fixed_wait", "none"]
    wait_seconds: float | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, ge=0)
    poll_interval_seconds: float | None = Field(default=None, ge=0)


class ErrorPayload(FlexibleContractModel):
    """步骤错误详情。"""

    type: str | None = None
    message: str | None = None
    detail: Any | None = None


class RunTraceRecord(ContractModel):
    """run_trace.jsonl 中的一条步骤级事实记录。"""

    timestamp: datetime
    session_id: NonEmptyStr
    workflow_id: NonEmptyStr
    step_id: NonEmptyStr
    view_id: str | None = None
    anchor_id: str | None = None
    action: ActionPayload
    wait_strategy: WaitStrategyPayload
    expected_text: str | list[str] | None = None
    actual_text: str | None = None
    match_mode: Literal["contains", "equals", "regex", "not_empty", "none"] = "none"
    confidence: float | None = Field(default=None, ge=0, le=1)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    matched: bool | None = None
    attempts: int = Field(default=1, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0)
    screenshot_path: str | None = None
    status: Literal["success", "timeout", "failed", "cancelled"]
    error: ErrorPayload | None = None
    provider_mode: str | None = None
    template_id: str | None = None
    template_version: str | None = None
