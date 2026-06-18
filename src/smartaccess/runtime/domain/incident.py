"""异常和恢复策略领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class IncidentType(StrEnum):
    """运行异常类型。"""

    WINDOW_MISSING = "WindowMissing"
    ANCHOR_MISSING = "AnchorMissing"
    OCR_LOW_CONFIDENCE = "OcrLowConfidence"
    SAFETY_LIMIT_VIOLATION = "SafetyLimitViolation"
    DEVICE_POPUP = "DevicePopup"
    PLATFORM_SYNC_FAILED = "PlatformSyncFailed"
    TEMPLATE_VERSION_MISSING = "TemplateVersionMissing"
    EXECUTOR_FAILED = "ExecutorFailed"


class RecoveryAction(StrEnum):
    """恢复动作。"""

    RETRY = "retry"
    ROLLBACK = "rollback"
    MANUAL_CONFIRM = "manual_confirm"
    ABORT = "abort"


DEFAULT_RECOVERY: dict[IncidentType, RecoveryAction] = {
    IncidentType.WINDOW_MISSING: RecoveryAction.RETRY,
    IncidentType.ANCHOR_MISSING: RecoveryAction.RETRY,
    IncidentType.OCR_LOW_CONFIDENCE: RecoveryAction.RETRY,
    IncidentType.SAFETY_LIMIT_VIOLATION: RecoveryAction.ABORT,
    IncidentType.DEVICE_POPUP: RecoveryAction.MANUAL_CONFIRM,
    IncidentType.PLATFORM_SYNC_FAILED: RecoveryAction.RETRY,
    IncidentType.TEMPLATE_VERSION_MISSING: RecoveryAction.ABORT,
    IncidentType.EXECUTOR_FAILED: RecoveryAction.RETRY,
}
MANUAL_CONFIRM_INCIDENTS = frozenset(
    {
        IncidentType.SAFETY_LIMIT_VIOLATION,
        IncidentType.DEVICE_POPUP,
        IncidentType.TEMPLATE_VERSION_MISSING,
    }
)


def default_recovery_for(incident_type: IncidentType) -> RecoveryAction:
    """返回异常类型默认恢复动作。"""

    return DEFAULT_RECOVERY.get(incident_type, RecoveryAction.MANUAL_CONFIRM)


def requires_manual_confirm(incident_type: IncidentType) -> bool:
    """返回异常类型是否需要人工确认。"""

    return incident_type in MANUAL_CONFIRM_INCIDENTS


@dataclass(slots=True)
class Incident:
    """运行时打开的一条异常记录。"""

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
        """创建异常并推导恢复动作。"""

        return cls(
            incident_id=incident_id,
            session_id=session_id,
            step_id=step_id,
            type=incident_type,
            detail=detail,
            recovery=default_recovery_for(incident_type),
            requires_manual_confirm=requires_manual_confirm(incident_type),
        )
