"""Domain state machine for the device-side experiment trigger/execute flow.

This is a framework-free port of the single-slot preparation model used by
the reference FastAPI service: only one experiment plan can be prepared at a
time, and an execute request is only valid after a successful preparation.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class PreparationStatus(StrEnum):
    """Lifecycle of the most recent experiment preparation."""

    IDLE = "idle"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class ExperimentError(RuntimeError):
    """Base class for experiment domain errors."""


class PreparationInProgressError(ExperimentError):
    """A new trigger arrived while a previous preparation was still running."""


class NotReadyToExecuteError(ExperimentError):
    """Execute was requested before a successful preparation."""


class InstructionGenerationError(ExperimentError):
    """Turning an experiment plan into local instructions failed."""


class ProcessExecutionError(ExperimentError):
    """The downstream process host could not be driven or read."""


@dataclass(slots=True)
class PreparationSnapshot:
    """Read-only projection of the current preparation state."""

    status: PreparationStatus
    request_id: str | None
    last_plan: str | None
    last_triggered_at: datetime | None
    completed_at: datetime | None
    error: str | None


@dataclass
class ExperimentPreparationState:
    """Tracks the last experiment plan submitted via the Edge API."""

    last_plan: str | None = None
    last_request_id: str | None = None
    last_triggered_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    _generating: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def begin_trigger(self, experiment_plan: str, request_id: str) -> None:
        """Claim the single preparation slot for a new plan."""

        with self._lock:
            if self._generating:
                raise PreparationInProgressError("上一轮指令解析任务仍在执行中")
            self.last_plan = experiment_plan
            self.last_request_id = request_id
            self.last_triggered_at = _utcnow()
            self.completed_at = None
            self.error = None
            self._generating = True

    def mark_done(self, error: str | None = None) -> None:
        """Release the preparation slot, recording an error if it failed."""

        with self._lock:
            self._generating = False
            self.completed_at = _utcnow()
            self.error = error

    def ensure_ready(self) -> None:
        """Raise ``NotReadyToExecuteError`` unless a preparation succeeded."""

        with self._lock:
            reason = self._not_ready_reason()
            if reason:
                raise NotReadyToExecuteError(reason)

    def status(self) -> PreparationStatus:
        with self._lock:
            return self._status_locked()

    def snapshot(self) -> PreparationSnapshot:
        with self._lock:
            return PreparationSnapshot(
                status=self._status_locked(),
                request_id=self.last_request_id,
                last_plan=self.last_plan,
                last_triggered_at=self.last_triggered_at,
                completed_at=self.completed_at,
                error=self.error,
            )

    def _status_locked(self) -> PreparationStatus:
        if self._generating:
            return PreparationStatus.GENERATING
        if self.error:
            return PreparationStatus.FAILED
        if self.completed_at is not None:
            return PreparationStatus.READY
        return PreparationStatus.IDLE

    def _not_ready_reason(self) -> str | None:
        if self.last_plan is None or self.last_triggered_at is None:
            return "请先调用 /api/v1/experiment/trigger 接口"
        if self._generating:
            return "指令解析仍在执行中"
        if self.completed_at is None:
            return "指令解析尚未完成"
        if self.error:
            return f"指令解析失败: {self.error}"
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
