"""IncidentService: open incidents, decide recovery, track manual confirms.

Wraps the incident/recovery domain rules (SPEC §9). Opening an incident derives
the default recovery action and whether it must escalate to a human; the
monitoring page drives :meth:`confirm` for blocked, high-risk recoveries.
"""

from __future__ import annotations

import uuid

from smartaccess.runtime.domain.incident import Incident, IncidentType, RecoveryAction
from smartaccess.shared.events import EventBus, RuntimeEventName


class IncidentService:
    """Tracks incidents raised during runs and their recovery decisions."""

    def __init__(self, *, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._incidents: dict[str, Incident] = {}

    def open(
        self, *, session_id: str, step_id: str, incident_type: IncidentType, detail: str
    ) -> Incident:
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

    def confirm(self, incident_id: str, *, action: RecoveryAction | None = None) -> Incident:
        """Resolve a blocked incident after a manual confirmation."""

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
        return [i for i in self._incidents.values() if not i.resolved]

    def all_incidents(self) -> list[Incident]:
        return list(self._incidents.values())
