"""SmartAccess v2 运行时事件名称。"""

from enum import StrEnum


class RuntimeEventName(StrEnum):
    """运行时发布的标准领域事件名。"""

    WORKFLOW_STANDARDIZED = "workflow.standardized"
    TEMPLATE_PUBLISHED = "template.published"
    RUN_CREATED = "run.created"
    RUN_READY = "run.ready"
    RUN_STARTED = "run.started"
    RUN_STEP_STARTED = "run.step.started"
    RUN_STEP_OBSERVED = "run.step.observed"
    RUN_STEP_SUCCEEDED = "run.step.succeeded"
    RUN_BLOCKED = "run.blocked"
    RUN_RECOVERED = "run.recovered"
    RUN_COMPLETED = "run.completed"
    RUN_STOPPING = "run.stopping"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"
    PLATFORM_SYNC_FAILED = "platform.sync.failed"
