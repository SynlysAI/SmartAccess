"""Workflow domain lifecycle and transition rules.

Models the full workflow lifecycle from PRD §9.1 and the transition guard the
application layer uses before moving a workflow between states.
"""

from __future__ import annotations

from enum import StrEnum


class WorkflowLifecycleState(StrEnum):
    """Lifecycle states a workflow moves through (PRD §9.1)."""

    DRAFT = "Draft"
    CALIBRATED = "Calibrated"
    STANDARDIZED = "Standardized"
    PUBLISHED = "Published"
    READY = "Ready"
    RUNNING = "Running"
    BLOCKED = "Blocked"
    RECOVERED = "Recovered"
    COMPLETED = "Completed"
    ARCHIVED = "Archived"

    @classmethod
    def from_contract(cls, value: str) -> "WorkflowLifecycleState":
        """Parse the ``metadata.lifecycle_state`` string from a contract."""

        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"未知的工作流生命周期状态: {value}") from exc


# Allowed forward transitions. The lifecycle is largely linear, but recovery can
# loop Blocked <-> Recovered -> Running, and any active state may be archived.
_TRANSITIONS: dict[WorkflowLifecycleState, set[WorkflowLifecycleState]] = {
    WorkflowLifecycleState.DRAFT: {WorkflowLifecycleState.CALIBRATED},
    WorkflowLifecycleState.CALIBRATED: {WorkflowLifecycleState.STANDARDIZED},
    WorkflowLifecycleState.STANDARDIZED: {WorkflowLifecycleState.PUBLISHED},
    WorkflowLifecycleState.PUBLISHED: {WorkflowLifecycleState.READY},
    WorkflowLifecycleState.READY: {WorkflowLifecycleState.RUNNING},
    WorkflowLifecycleState.RUNNING: {
        WorkflowLifecycleState.BLOCKED,
        WorkflowLifecycleState.COMPLETED,
    },
    WorkflowLifecycleState.BLOCKED: {
        WorkflowLifecycleState.RECOVERED,
        WorkflowLifecycleState.COMPLETED,
    },
    WorkflowLifecycleState.RECOVERED: {
        WorkflowLifecycleState.RUNNING,
        WorkflowLifecycleState.COMPLETED,
    },
    WorkflowLifecycleState.COMPLETED: {WorkflowLifecycleState.ARCHIVED},
    WorkflowLifecycleState.ARCHIVED: set(),
}


def can_transition(
    current: WorkflowLifecycleState, target: WorkflowLifecycleState
) -> bool:
    """Return whether ``current -> target`` is an allowed lifecycle move."""

    return target in _TRANSITIONS.get(current, set())
