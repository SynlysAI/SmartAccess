"""Incident and recovery domain rules (SPEC §9).

Encodes the incident taxonomy, the recovery action vocabulary, and the default
recovery decision per incident type. The runtime ``RecoveryEngine`` consumes
``default_recovery_for`` and escalates high-risk recoveries to manual confirm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class IncidentType(StrEnum):
    """Incident taxonomy from SPEC §9."""

    WINDOW_MISSING = "WindowMissing"
    ANCHOR_MISSING = "AnchorMissing"
    OCR_LOW_CONFIDENCE = "OcrLowConfidence"
    SAFETY_LIMIT_VIOLATION = "SafetyLimitViolation"
    PLATFORM_SYNC_FAILED = "PlatformSyncFailed"
    TEMPLATE_VERSION_MISSING = "TemplateVersionMissing"
    EXECUTOR_FAILED = "ExecutorFailed"


class RecoveryAction(StrEnum):
    """The four recovery actions SmartAccess may take (PRD §8.8)."""

    RETRY = "retry"
    ROLLBACK = "rollback"
    MANUAL_CONFIRM = "manual_confirm"
    ABORT = "abort"


# Default recovery per incident type (SPEC §9 "默认处理" column).
_DEFAULT_RECOVERY: dict[IncidentType, RecoveryAction] = {
    IncidentType.WINDOW_MISSING: RecoveryAction.RETRY,
    IncidentType.ANCHOR_MISSING: RecoveryAction.RETRY,
    IncidentType.OCR_LOW_CONFIDENCE: RecoveryAction.RETRY,
    IncidentType.SAFETY_LIMIT_VIOLATION: RecoveryAction.ABORT,
    IncidentType.PLATFORM_SYNC_FAILED: RecoveryAction.RETRY,
    IncidentType.TEMPLATE_VERSION_MISSING: RecoveryAction.ABORT,
    IncidentType.EXECUTOR_FAILED: RecoveryAction.RETRY,
}

# Incident types whose recovery must wait for a human before continuing.
_REQUIRES_MANUAL_CONFIRM: frozenset[IncidentType] = frozenset(
    {
        IncidentType.SAFETY_LIMIT_VIOLATION,
        IncidentType.TEMPLATE_VERSION_MISSING,
    }
)


def default_recovery_for(incident_type: IncidentType) -> RecoveryAction:
    """Return the default recovery action for ``incident_type``."""

    return _DEFAULT_RECOVERY.get(incident_type, RecoveryAction.MANUAL_CONFIRM)


def requires_manual_confirm(incident_type: IncidentType) -> bool:
    """Whether this incident class must escalate to a manual confirmation."""

    return incident_type in _REQUIRES_MANUAL_CONFIRM


@dataclass(slots=True)
class Incident:
    """A single incident raised during a run, with its recovery decision."""

    incident_id: str
    session_id: str
    step_id: str
    type: IncidentType
    detail: str
    recovery: RecoveryAction
    requires_manual_confirm: bool = False
    resolved: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def open(
        cls,
        *,
        incident_id: str,
        session_id: str,
        step_id: str,
        incident_type: IncidentType,
        detail: str,
    ) -> "Incident":
        """Open an incident, deriving the default recovery + escalation flag."""

        return cls(
            incident_id=incident_id,
            session_id=session_id,
            step_id=step_id,
            type=incident_type,
            detail=detail,
            recovery=default_recovery_for(incident_type),
            requires_manual_confirm=requires_manual_confirm(incident_type),
        )
