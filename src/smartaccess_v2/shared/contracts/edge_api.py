"""设备侧 FastAPI 接口契约模型。"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import ContractModel, NonEmptyStr


class TriggerGenerateRequest(ContractModel):
    """`/api/v1/experiment/trigger` 请求体。"""

    experiment_plan: NonEmptyStr
    request_id: str | None = None


class ExecuteRequest(ContractModel):
    """`/api/v1/experiment/execute` 请求体。"""

    request_id: str | None = None


class HealthResponse(ContractModel):
    """`/health` 响应体。"""

    ok: bool
    service: NonEmptyStr
    timestamp: NonEmptyStr
    udp_target: dict[str, Any]


class ApiResponse(ContractModel):
    """触发和执行接口的通用响应体。"""

    ok: bool
    message: NonEmptyStr
    request_id: NonEmptyStr
    signal: NonEmptyStr
    udp_ack: Any | None = None
    timestamp: NonEmptyStr
    instructions: list[str] | None = None


class StatusResponse(ContractModel):
    """`/api/v1/experiment/status` 轮询响应体。"""

    ok: bool
    request_id: str | None = None
    status: NonEmptyStr
    detail: NonEmptyStr
    current_command: str = Field(default="")
    last_plan_updated_at: str | None = None
    last_triggered_at: str | None = None
    generated_at: NonEmptyStr
