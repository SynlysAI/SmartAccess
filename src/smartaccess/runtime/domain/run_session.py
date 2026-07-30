"""运行会话领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from smartaccess.shared.events.runtime import RuntimeEventName


class RunSessionStatus(StrEnum):
    """运行会话粗粒度状态。"""

    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    STOPPING = "stopping"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class RunStepStatus(StrEnum):
    """运行步骤状态。"""

    PENDING = "pending"
    RUNNING = "running"
    OBSERVED = "observed"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class RunStep:
    """运行会话中的一个步骤投影。"""

    step_id: str
    action: str
    status: RunStepStatus = RunStepStatus.PENDING


EVENT_STATUS: dict[RuntimeEventName, RunSessionStatus] = {
    RuntimeEventName.RUN_CREATED: RunSessionStatus.CREATED,
    RuntimeEventName.RUN_READY: RunSessionStatus.READY,
    RuntimeEventName.RUN_STARTED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_STEP_STARTED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_STEP_OBSERVED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_STEP_SUCCEEDED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_BLOCKED: RunSessionStatus.BLOCKED,
    RuntimeEventName.RUN_RECOVERED: RunSessionStatus.RUNNING,
    RuntimeEventName.RUN_STOPPING: RunSessionStatus.STOPPING,
    RuntimeEventName.RUN_CANCELLED: RunSessionStatus.CANCELLED,
    RuntimeEventName.RUN_COMPLETED: RunSessionStatus.COMPLETED,
    RuntimeEventName.RUN_FAILED: RunSessionStatus.FAILED,
}


@dataclass(slots=True)
class RunSession:
    """绑定到工作流的一次运行会话。"""

    session_id: str
    workflow_id: str
    device_id: str | None = None
    author: str | None = None
    workflow_name: str | None = None
    template_id: str | None = None
    template_version: str | None = None
    status: RunSessionStatus = RunSessionStatus.CREATED
    steps: list[RunStep] = field(default_factory=list)
    emitted_events: list[RuntimeEventName] = field(default_factory=list)

    def apply(self, event: RuntimeEventName) -> None:
        """根据事件推进会话状态。"""

        self.emitted_events.append(event)
        next_status = EVENT_STATUS.get(event)
        if next_status is not None:
            self.status = next_status

    def archive(self) -> None:
        """归档运行会话。"""

        self.status = RunSessionStatus.ARCHIVED
