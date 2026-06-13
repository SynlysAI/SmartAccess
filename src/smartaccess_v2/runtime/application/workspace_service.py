"""工作区概览投影服务。"""

from __future__ import annotations

from dataclasses import dataclass, field

from smartaccess_v2.runtime.application.anchor_service import AnchorService
from smartaccess_v2.runtime.application.incident_service import IncidentService
from smartaccess_v2.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess_v2.runtime.application.run_session_service import RunSessionService
from smartaccess_v2.runtime.application.template_service import TemplateService
from smartaccess_v2.runtime.application.workflow_service import WorkflowService


@dataclass(slots=True)
class DeviceStatus:
    """设备状态摘要。"""

    device_id: str
    status: str


@dataclass(slots=True)
class DashboardProjection:
    """运行概览页投影。"""

    devices: list[DeviceStatus] = field(default_factory=list)
    recent_runs: list[dict[str, str]] = field(default_factory=list)
    incidents: list[dict[str, str]] = field(default_factory=list)
    workflow_count: int = 0
    template_count: int = 0
    local_template_count: int = 0
    cloud_template_count: int = 0
    template_sync_failed: int = 0
    cloud_templates_available: bool = False
    outbox_pending: int = 0
    outbox_failed: int = 0


class WorkspaceService:
    """聚合工作区只读概览数据。"""

    def __init__(
        self,
        *,
        anchors: AnchorService,
        workflows: WorkflowService,
        templates: TemplateService,
        run_sessions: RunSessionService,
        incidents: IncidentService,
        platform_sync: PlatformSyncService,
    ) -> None:
        """初始化工作区服务。"""

        self._anchors = anchors
        self._workflows = workflows
        self._templates = templates
        self._run_sessions = run_sessions
        self._incidents = incidents
        self._platform_sync = platform_sync

    def dashboard(self) -> DashboardProjection:
        """返回工作区概览投影。"""

        template_stats = self._templates.stats()
        sync_stats = self._platform_sync.stats()
        return DashboardProjection(
            devices=[
                DeviceStatus(device_id=profile.profile_id, status="Draft")
                for profile in self._anchors.list_profiles()
            ],
            recent_runs=[
                {
                    "session_id": session.session_id,
                    "workflow_id": session.workflow_id,
                    "status": session.status.value,
                }
                for session in self._run_sessions.recent()
            ],
            incidents=[
                {
                    "incident_id": incident.incident_id,
                    "session_id": incident.session_id,
                    "type": incident.type.value,
                    "detail": incident.detail,
                }
                for incident in self._incidents.open_incidents()
            ],
            workflow_count=len(self._workflows.list_workflows()),
            template_count=len(self._templates.list_all()),
            local_template_count=template_stats.local_count,
            cloud_template_count=template_stats.cloud_count,
            template_sync_failed=template_stats.failed_count,
            cloud_templates_available=template_stats.cloud_available,
            outbox_pending=sync_stats.pending,
            outbox_failed=sync_stats.failed,
        )
