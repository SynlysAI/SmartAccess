"""设备侧 Edge API。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, FastAPI

from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.shared.contracts.edge_api import (
    ApiResponse,
    ExecuteRequest,
    HealthResponse,
    StatusResponse,
    TriggerGenerateRequest,
)

SIGNAL_TRIGGER = "generate_instruction"
SIGNAL_EXECUTE = "execute_process"


class EdgeApiState:
    """Edge API 进程内状态。"""

    def __init__(self, facade: RuntimeFacade) -> None:
        """初始化 API 状态。

        Args:
            facade: 运行时门面。
        """

        self.facade = facade
        self.last_request_id: str | None = None
        self.last_plan_updated_at: str | None = None
        self.last_triggered_at: str | None = None
        self.instructions: list[str] = []
        self.status = "idle"
        self.detail = "等待任务"
        self.current_command = ""


def create_edge_app(facade: RuntimeFacade) -> FastAPI:
    """创建独立 Edge API 应用。

    Args:
        facade: 运行时门面。

    Returns:
        FastAPI 应用。
    """

    app = FastAPI(title="SmartAccess Edge API")
    app.include_router(create_edge_router(facade))
    return app


def create_edge_router(facade: RuntimeFacade) -> APIRouter:
    """创建 Edge API 路由。

    Args:
        facade: 运行时门面。

    Returns:
        FastAPI 路由。
    """

    router = APIRouter()
    state = EdgeApiState(facade)

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """返回服务健康状态。"""

        return HealthResponse(
            ok=True,
            service="SmartAccess",
            timestamp=_now(),
            udp_target=_udp_target(facade),
        )

    @router.post("/api/v1/experiment/trigger", response_model=ApiResponse)
    def trigger(request: TriggerGenerateRequest) -> ApiResponse:
        """接收实验计划并生成本地执行指令。"""

        request_id = request.request_id or _request_id()
        state.last_request_id = request_id
        state.last_plan_updated_at = _now()
        state.status = "generated"
        state.detail = "实验计划已接收"
        state.instructions = _instructions_from_plan(request.experiment_plan)
        return ApiResponse(
            ok=True,
            message="实验计划已接收",
            request_id=request_id,
            signal=SIGNAL_TRIGGER,
            timestamp=_now(),
            instructions=state.instructions,
        )

    @router.post("/api/v1/experiment/execute", response_model=ApiResponse)
    def execute(request: ExecuteRequest) -> ApiResponse:
        """触发执行最近生成的指令。"""

        request_id = request.request_id or state.last_request_id or _request_id()
        state.last_request_id = request_id
        state.last_triggered_at = _now()
        state.status = "executing"
        state.detail = "执行信号已发送"
        state.current_command = state.instructions[0] if state.instructions else ""
        return ApiResponse(
            ok=True,
            message="执行信号已发送",
            request_id=request_id,
            signal=SIGNAL_EXECUTE,
            timestamp=_now(),
            instructions=state.instructions or None,
        )

    @router.get("/api/v1/experiment/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        """返回最近一次实验触发状态。"""

        return StatusResponse(
            ok=True,
            request_id=state.last_request_id,
            status=state.status,
            detail=state.detail,
            current_command=state.current_command,
            last_plan_updated_at=state.last_plan_updated_at,
            last_triggered_at=state.last_triggered_at,
            generated_at=_now(),
        )

    return router


def _instructions_from_plan(experiment_plan: str) -> list[str]:
    """把实验计划切分成基础指令列表。

    Args:
        experiment_plan: 实验计划文本。

    Returns:
        指令列表。
    """

    lines = [
        line.strip(" -\t")
        for line in experiment_plan.splitlines()
        if line.strip(" -\t")
    ]
    return lines or [experiment_plan.strip()]


def _udp_target(facade: RuntimeFacade) -> dict[str, Any]:
    """返回兼容旧接口的 UDP 目标摘要。"""

    settings = facade.settings()
    return {
        "enabled": True,
        "host": settings.udp_host,
        "port": settings.udp_port,
    }


def _request_id() -> str:
    """生成请求 ID。"""

    return f"req_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    """返回当前 UTC ISO 时间。"""

    return datetime.now(timezone.utc).isoformat()
