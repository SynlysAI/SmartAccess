"""ExperimentService: device-side experiment trigger/execute/status use case.

This is the use-case layer behind the Edge API. It owns the preparation state
machine, delegates instruction generation and process control to injected
ports, and maps results onto the shared ``edge_api`` contract models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from smartaccess_v2.runtime.domain.experiment import (
    ExperimentPreparationState,
    InstructionGenerationError,
)
from smartaccess_v2.shared.contracts.edge_api import (
    ApiResponse,
    ExecuteRequest,
    HealthResponse,
    StatusResponse,
    TriggerGenerateRequest,
)

from .ports import InstructionGenerator, ProcessExecutorClient

_SERVICE_NAME = "smartaccess-edge"
_TRIGGER_SIGNAL = "TRIGGER_GENERATE_LOCAL"
_EXECUTE_SIGNAL = "EXECUTE_PROCESS_FILE"


class ExperimentService:
    """Coordinates the trigger -> execute -> status flow for the Edge API."""

    def __init__(
        self,
        *,
        instruction_generator: InstructionGenerator,
        executor_client: ProcessExecutorClient,
        udp_target: dict[str, Any] | None = None,
        state: ExperimentPreparationState | None = None,
    ) -> None:
        self._instructions = instruction_generator
        self._executor = executor_client
        self._udp_target: dict[str, Any] = dict(udp_target or {})
        self._state = state or ExperimentPreparationState()

    def health(self) -> HealthResponse:
        return HealthResponse(
            ok=True,
            service=_SERVICE_NAME,
            timestamp=_now_iso(),
            udp_target=self._udp_target,
        )

    def trigger(self, request: TriggerGenerateRequest) -> ApiResponse:
        request_id = request.request_id or _new_request_id()
        self._state.begin_trigger(request.experiment_plan, request_id)
        try:
            result = self._instructions.generate(request.experiment_plan)
        except Exception as exc:  # noqa: BLE001 - normalize to a domain failure
            self._state.mark_done(error=str(exc))
            raise InstructionGenerationError(f"指令解析失败: {exc}") from exc
        self._state.mark_done()

        return ApiResponse(
            ok=True,
            message="本地指令解析任务已完成。",
            request_id=request_id,
            signal=_TRIGGER_SIGNAL,
            udp_ack=None,
            timestamp=_now_iso(),
            instructions=result.instructions,
        )

    def execute(self, request: ExecuteRequest | None = None) -> ApiResponse:
        request_id = (request.request_id if request else None) or _new_request_id()
        self._state.ensure_ready()
        ack = self._executor.execute_process()

        return ApiResponse(
            ok=True,
            message="工艺流程执行命令已下发，请通过 /api/v1/experiment/status 查询进度。",
            request_id=request_id,
            signal=_EXECUTE_SIGNAL,
            udp_ack=ack,
            timestamp=_now_iso(),
        )

    def status(self) -> StatusResponse:
        execution = self._executor.read_execution_state()
        snapshot = self._state.snapshot()
        triggered_iso = (
            snapshot.last_triggered_at.isoformat() if snapshot.last_triggered_at else None
        )

        return StatusResponse(
            ok=True,
            request_id=snapshot.request_id,
            status=execution.status,
            detail=execution.detail,
            current_command=execution.current_command,
            last_plan_updated_at=triggered_iso,
            last_triggered_at=triggered_iso,
            generated_at=_now_iso(),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_request_id() -> str:
    return str(uuid.uuid4())

