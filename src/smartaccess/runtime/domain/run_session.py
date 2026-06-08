"""RunSession aggregate and its event-driven state machine.

Tracks the high-level state of one execution session, its steps, and the domain
events it has emitted. Persistence (SQLite + ``run_trace.jsonl``) lives in the
adapter/service layers; this aggregate owns the in-memory truth and the state
transitions driven by :class:`RuntimeEventName`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from smartaccess.shared.events.runtime import RuntimeEventName


class RunSessionStatus(StrEnum):
    """Coarse session state surfaced to monitoring and platform sync."""

    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class RunStepStatus(StrEnum):
    """Per-step execution state for the monitoring timeline."""

    PENDING = "pending"
    RUNNING = "running"
    OBSERVED = "observed"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(slots=True)
class RunStep:
    """Projection of one workflow step inside a session."""

    step_id: str
    action: str
    status: RunStepStatus = RunStepStatus.PENDING


# How runtime events move the session status forward.
_EVENT_STATUS: dict[RuntimeEventName, RunSessionStatus] = {
    RuntimeEventName.RUN_CREATED: RunSessionStatus.CREATED,
    RuntimeEventName.RUN_READY: RunSessionStatus.READY,
    RuntimeEventName.RUN_STEP_STARTED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_STEP_OBSERVED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_STEP_SUCCEEDED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_BLOCKED: RunSessionStatus.BLOCKED,
    RuntimeEventName.RUN_RECOVERED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_COMPLETED: RunSessionStatus.COMPLETED,
    RuntimeEventName.RUN_FAILED: RunSessionStatus.FAILED,
}


@dataclass
class RunSession:
    """One execution session bound to a workflow (and optional template)."""

    session_id: str
    workflow_id: str
    template_id: str | None = None
    template_version: str | None = None
    status: RunSessionStatus = RunSessionStatus.CREATED
    steps: list[RunStep] = field(default_factory=list)
    emitted_events: list[RuntimeEventName] = field(default_factory=list)

    def apply(self, event: RuntimeEventName) -> None:
        """Advance session status according to ``event`` and record it."""

        self.emitted_events.append(event)
        next_status = _EVENT_STATUS.get(event)
        if next_status is not None:
            self.status = next_status

    def archive(self) -> None:
        self.status = RunSessionStatus.ARCHIVED
