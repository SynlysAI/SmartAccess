"""Pydantic models for the device-side FastAPI MVP interface."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .base import ContractModel, NonEmptyStr


class TriggerGenerateRequest(ContractModel):
    """Request payload for `/api/v1/experiment/trigger`."""

    experiment_plan: NonEmptyStr
    request_id: str | None = None


class ExecuteRequest(ContractModel):
    """Request payload for `/api/v1/experiment/execute`."""

    request_id: str | None = None


class HealthResponse(ContractModel):
    """Response payload for `/health`."""

    ok: bool
    service: NonEmptyStr
    timestamp: NonEmptyStr
    udp_target: dict[str, Any]


class ApiResponse(ContractModel):
    """Generic operation response for trigger and execute endpoints."""

    ok: bool
    message: NonEmptyStr
    request_id: NonEmptyStr
    signal: NonEmptyStr
    udp_ack: Any | None = None
    timestamp: NonEmptyStr
    instructions: list[str] | None = None


class StatusResponse(ContractModel):
    """Polling response for `/api/v1/experiment/status`."""

    ok: bool
    request_id: str | None = None
    status: NonEmptyStr
    detail: NonEmptyStr
    current_command: str = Field(default="")
    last_plan_updated_at: str | None = None
    last_triggered_at: str | None = None
    generated_at: NonEmptyStr
