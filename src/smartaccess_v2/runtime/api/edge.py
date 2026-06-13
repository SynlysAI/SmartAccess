"""设备侧 Edge API。"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException

from smartaccess_v2.runtime.adapters import (
    EchoInstructionGenerator,
    StubProcessExecutorClient,
    UdpProcessExecutorClient,
)
from smartaccess_v2.runtime.application.experiment_service import ExperimentService
from smartaccess_v2.runtime.application.facade import RuntimeFacade
from smartaccess_v2.runtime.domain.experiment import (
    InstructionGenerationError,
    NotReadyToExecuteError,
    PreparationInProgressError,
    ProcessExecutionError,
)
from smartaccess_v2.shared.contracts.edge_api import (
    ApiResponse,
    ExecuteRequest,
    HealthResponse,
    StatusResponse,
    TriggerGenerateRequest,
)


def create_edge_app(service: ExperimentService | RuntimeFacade) -> FastAPI:
    """创建独立 Edge API 应用。

    Args:
        service: 实验触发服务，或用于兼容旧 v2 调用的运行时门面。

    Returns:
        FastAPI 应用。
    """

    app = FastAPI(
        title="SmartAccess Edge API",
        version="0.1.0",
        description="设备侧实验触发、执行与状态查询接口",
    )
    app.include_router(create_edge_router(service))
    return app


def create_edge_router(service: ExperimentService | RuntimeFacade) -> APIRouter:
    """创建 Edge API 路由。

    Args:
        service: 实验触发服务，或用于兼容旧 v2 调用的运行时门面。

    Returns:
        FastAPI 路由。
    """

    router = APIRouter()
    experiment_service = _coerce_service(service)

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """返回服务健康状态。"""

        return experiment_service.health()

    @router.post("/api/v1/experiment/trigger", response_model=ApiResponse)
    def trigger(request: TriggerGenerateRequest) -> ApiResponse:
        """接收实验计划并生成本地执行指令。"""

        try:
            return experiment_service.trigger(request)
        except PreparationInProgressError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InstructionGenerationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/api/v1/experiment/execute", response_model=ApiResponse)
    def execute(request: ExecuteRequest | None = None) -> ApiResponse:
        """触发执行最近生成的指令。"""

        try:
            return experiment_service.execute(request)
        except NotReadyToExecuteError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProcessExecutionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/api/v1/experiment/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        """返回最近一次实验触发状态。"""

        try:
            return experiment_service.status()
        except ProcessExecutionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router


def _coerce_service(service: ExperimentService | RuntimeFacade) -> ExperimentService:
    """把兼容输入转换为实验触发服务。

    Args:
        service: 实验触发服务或运行时门面。

    Returns:
        实验触发服务。
    """

    if isinstance(service, ExperimentService):
        return service
    settings = service.settings()
    enabled = settings.process_executor_provider.lower() == "udp"
    executor = (
        UdpProcessExecutorClient(
            host=settings.udp_host,
            port=settings.udp_port,
            timeout_s=settings.udp_timeout_seconds,
        )
        if enabled
        else StubProcessExecutorClient()
    )
    return ExperimentService(
        instruction_generator=EchoInstructionGenerator(),
        executor_client=executor,
        udp_target={
            "enabled": enabled,
            "host": settings.udp_host,
            "port": settings.udp_port,
        },
    )
