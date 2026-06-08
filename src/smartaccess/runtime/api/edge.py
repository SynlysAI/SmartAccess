"""Device-side Edge API (FastAPI) built on the shared ``edge_api`` contracts.

Exposes the four MVP baseline endpoints from the software design doc:
``GET /health``, ``POST /api/v1/experiment/trigger``,
``POST /api/v1/experiment/execute`` and ``GET /api/v1/experiment/status``.

All request/response schemas come from ``smartaccess.shared.contracts.edge_api``
rather than being declared inline; the route handlers stay thin and delegate to
:class:`ExperimentService`, translating domain errors to HTTP status codes.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from smartaccess.runtime.application.experiment_service import ExperimentService
from smartaccess.runtime.domain.experiment import (
    InstructionGenerationError,
    NotReadyToExecuteError,
    PreparationInProgressError,
    ProcessExecutionError,
)
from smartaccess.shared.contracts.edge_api import (
    ApiResponse,
    ExecuteRequest,
    HealthResponse,
    StatusResponse,
    TriggerGenerateRequest,
)


def create_edge_app(service: ExperimentService) -> FastAPI:
    """Build the FastAPI app wiring the four edge endpoints to ``service``."""

    app = FastAPI(
        title="SmartAccess Edge API",
        version="0.1.0",
        description="设备侧实验触发、执行与状态查询接口",
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return service.health()

    @app.post("/api/v1/experiment/trigger", response_model=ApiResponse)
    def trigger(request: TriggerGenerateRequest) -> ApiResponse:
        try:
            return service.trigger(request)
        except PreparationInProgressError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InstructionGenerationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/v1/experiment/execute", response_model=ApiResponse)
    def execute(request: ExecuteRequest | None = None) -> ApiResponse:
        try:
            return service.execute(request)
        except NotReadyToExecuteError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProcessExecutionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/v1/experiment/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        try:
            return service.status()
        except ProcessExecutionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app
