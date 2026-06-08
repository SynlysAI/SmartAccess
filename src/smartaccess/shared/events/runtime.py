"""Runtime event names aligned with the software design document."""

from enum import StrEnum


class RuntimeEventName(StrEnum):
    """Canonical domain event names emitted by SmartAccess runtime."""

    WORKFLOW_STANDARDIZED = "workflow.standardized"
    TEMPLATE_PUBLISHED = "template.published"
    RUN_CREATED = "run.created"
    RUN_READY = "run.ready"
    RUN_STEP_STARTED = "run.step.started"
    RUN_STEP_OBSERVED = "run.step.observed"
    RUN_STEP_SUCCEEDED = "run.step.succeeded"
    RUN_BLOCKED = "run.blocked"
    RUN_RECOVERED = "run.recovered"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    PLATFORM_SYNC_FAILED = "platform.sync.failed"
