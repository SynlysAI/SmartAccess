"""运行异常服务。"""

from __future__ import annotations

import uuid

from smartaccess_v2.runtime.domain.incident import (
    Incident,
    IncidentType,
    RecoveryAction,
)
from smartaccess_v2.shared.events.bus import EventBus
from smartaccess_v2.shared.events.runtime import RuntimeEventName


class IncidentService:
    """记录运行异常及恢复决策。"""

    def __init__(self, *, event_bus: EventBus) -> None:
        """初始化异常服务。"""

        self._event_bus = event_bus
        self._incidents: dict[str, Incident] = {}

    def open(
        self,
        *,
        session_id: str,
        step_id: str,
        incident_type: IncidentType,
        detail: str,
    ) -> Incident:
        """打开一条异常。"""

        incident = Incident.open(
            incident_id=f"inc_{uuid.uuid4().hex[:10]}",
            session_id=session_id,
            step_id=step_id,
            incident_type=incident_type,
            detail=detail,
        )
        self._incidents[incident.incident_id] = incident
        if incident.requires_manual_confirm:
            self._event_bus.emit(
                RuntimeEventName.RUN_BLOCKED,
                session_id=session_id,
                step_id=step_id,
                incident_id=incident.incident_id,
                incident_type=incident_type.value,
                detail=detail,
            )
        return incident

    def confirm(
        self,
        incident_id: str,
        *,
        action: RecoveryAction | None = None,
    ) -> Incident:
        """人工确认并关闭异常。"""

        incident = self._incidents[incident_id]
        if action is not None:
            incident.recovery = action
        incident.resolved = True
        self._event_bus.emit(
            RuntimeEventName.RUN_RECOVERED,
            session_id=incident.session_id,
            step_id=incident.step_id,
            incident_id=incident.incident_id,
            recovery=incident.recovery.value,
        )
        return incident

    def open_incidents(self) -> list[Incident]:
        """返回未关闭异常。"""

        return [incident for incident in self._incidents.values() if not incident.resolved]

    def all_incidents(self) -> list[Incident]:
        """返回全部异常。"""

        return list(self._incidents.values())
