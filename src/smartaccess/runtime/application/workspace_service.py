"""WorkspaceService: dashboard projection for the workbench home page.

Aggregates read-only state from the other services into the projection the
dashboard page renders: device status, recent runs, open incidents, template
counts, and outbox alerts (PRD §8.9, design §9.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from smartaccess.runtime.application.calibration_service import CalibrationService
from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess.runtime.application.run_session_service import RunSessionService
from smartaccess.runtime.application.template_service import TemplateService


@dataclass(slots=True)
class DeviceStatus:
    device_id: str
    status: str


@dataclass(slots=True)
class RecentRun:
    session_id: str
    workflow_id: str
    status: str


@dataclass(slots=True)
class IncidentAlert:
    incident_id: str
    session_id: str
    type: str
    detail: str


@dataclass(slots=True)
class DashboardProjection:
    devices: list[DeviceStatus] = field(default_factory=list)
    recent_runs: list[RecentRun] = field(default_factory=list)
    incidents: list[IncidentAlert] = field(default_factory=list)
    template_count: int = 0
    local_template_count: int = 0
    cloud_template_count: int = 0
    template_sync_failed: int = 0
    cloud_templates_available: bool = False
    outbox_pending: int = 0
    outbox_failed: int = 0


class WorkspaceService:
    """Builds the dashboard projection from the other services."""

    def __init__(
        self,
        *,
        calibration: CalibrationService,
        run_sessions: RunSessionService,
        incidents: IncidentService,
        templates: TemplateService,
        platform_sync: PlatformSyncService,
    ) -> None:
        self._calibration = calibration
        self._run_sessions = run_sessions
        self._incidents = incidents
        self._templates = templates
        self._platform_sync = platform_sync

    def dashboard(self) -> DashboardProjection:
        sync = self._platform_sync.stats()
        template_stats = self._templates.stats()
        return DashboardProjection(
            devices=[
                DeviceStatus(
                    device_id=p.device_id,
                    status=(self._calibration.status_of(p.device_id) or "Draft"),
                )
                for p in self._calibration.list_profiles()
            ],
            recent_runs=[
                RecentRun(
                    session_id=s.session_id,
                    workflow_id=s.workflow_id,
                    status=s.status.value,
                )
                for s in self._run_sessions.recent()
            ],
            incidents=[
                IncidentAlert(
                    incident_id=i.incident_id,
                    session_id=i.session_id,
                    type=i.type.value,
                    detail=i.detail,
                )
                for i in self._incidents.open_incidents()
            ],
            template_count=len(self._templates.list_all()),
            local_template_count=template_stats.local_count,
            cloud_template_count=template_stats.cloud_count,
            template_sync_failed=template_stats.failed_count,
            cloud_templates_available=template_stats.cloud_available,
            outbox_pending=sync.pending,
            outbox_failed=sync.failed,
        )
