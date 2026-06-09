"""UI projections for the workflow journey landing page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from smartaccess.runtime.application.workspace_service import DashboardProjection
from smartaccess.runtime.application.template_service import TemplateRecord
from smartaccess.runtime.application.workflow_service import StandardizationResult
from smartaccess.shared.contracts.workflow import WorkflowContract

JourneyStageStatus = Literal["completed", "current", "blocked", "future"]
JourneyStageId = Literal["calibration", "workflow", "template", "monitoring"]


@dataclass(frozen=True, slots=True)
class JourneyStageProjection:
    stage_id: JourneyStageId
    title: str
    meta: str
    description: str
    status: JourneyStageStatus
    target_page_index: int


@dataclass(frozen=True, slots=True)
class JourneyProjection:
    stages: list[JourneyStageProjection]
    summary: str
    cta_label: str
    cta_target_page_index: int


_STAGE_TITLES: dict[JourneyStageId, str] = {
    "calibration": "设备接入与校准",
    "workflow": "工作流设计",
    "template": "模板发布",
    "monitoring": "执行监控",
}

_STAGE_PAGE_INDEX: dict[JourneyStageId, int] = {
    "calibration": 1,
    "workflow": 2,
    "template": 3,
    "monitoring": 4,
}

_STAGE_DESCRIPTIONS: dict[JourneyStageId, str] = {
    "calibration": "识别窗口、标注 ROI、保存仪器画像",
    "workflow": "生成步骤、绑定锚点、通过标准化预检",
    "template": "发布可复用模板，沉淀到模板中心",
    "monitoring": "执行、观察、恢复，并闭环记录运行状态",
}

_STATUS_LABEL: dict[JourneyStageStatus, str] = {
    "completed": "已完成",
    "current": "当前步骤",
    "blocked": "存在阻塞",
    "future": "后续步骤",
}


def build_journey_projection(
    dashboard: DashboardProjection,
    workflows: list[WorkflowContract],
    workflow_checks: dict[str, StandardizationResult],
    templates: list[TemplateRecord],
) -> JourneyProjection:
    has_devices = bool(dashboard.devices)
    latest_device = dashboard.devices[-1].device_id if dashboard.devices else "未开始"

    valid_workflows = [
        workflow for workflow in workflows if workflow_checks.get(workflow.metadata.workflow_id, StandardizationResult(False, [])).ok
    ]
    invalid_workflows = [
        workflow for workflow in workflows if workflow.metadata.workflow_id not in {wf.metadata.workflow_id for wf in valid_workflows}
    ]
    latest_workflow = workflows[-1].metadata.workflow_id if workflows else "未开始"

    published_templates = [record for record in templates if record.status.value == "Published"]
    failed_templates = [record for record in templates if record.error]
    latest_template = str(templates[-1].identity) if templates else "未开始"

    latest_run = dashboard.recent_runs[-1] if dashboard.recent_runs else None
    latest_run_status = latest_run.status if latest_run is not None else "未开始"
    has_incidents = bool(dashboard.incidents)

    calibration_status: JourneyStageStatus = "completed" if has_devices else "current"

    if not has_devices:
        workflow_status: JourneyStageStatus = "future"
    elif valid_workflows:
        workflow_status = "completed"
    elif invalid_workflows:
        workflow_status = "blocked"
    else:
        workflow_status = "current"

    if workflow_status != "completed":
        template_status: JourneyStageStatus = "future"
    elif published_templates:
        template_status = "completed"
    elif failed_templates:
        template_status = "blocked"
    else:
        template_status = "current"

    if template_status != "completed":
        monitoring_status: JourneyStageStatus = "future"
    elif has_incidents or latest_run_status in {"blocked", "failed"}:
        monitoring_status = "blocked"
    elif latest_run_status == "completed":
        monitoring_status = "completed"
    elif latest_run_status in {"created", "ready", "running"}:
        monitoring_status = "current"
    else:
        monitoring_status = "current"

    stages = [
        JourneyStageProjection(
            stage_id="calibration",
            title=_STAGE_TITLES["calibration"],
            meta=latest_device,
            description=_STAGE_DESCRIPTIONS["calibration"],
            status=calibration_status,
            target_page_index=_STAGE_PAGE_INDEX["calibration"],
        ),
        JourneyStageProjection(
            stage_id="workflow",
            title=_STAGE_TITLES["workflow"],
            meta=latest_workflow,
            description=_STAGE_DESCRIPTIONS["workflow"],
            status=workflow_status,
            target_page_index=_STAGE_PAGE_INDEX["workflow"],
        ),
        JourneyStageProjection(
            stage_id="template",
            title=_STAGE_TITLES["template"],
            meta=latest_template,
            description=_STAGE_DESCRIPTIONS["template"],
            status=template_status,
            target_page_index=_STAGE_PAGE_INDEX["template"],
        ),
        JourneyStageProjection(
            stage_id="monitoring",
            title=_STAGE_TITLES["monitoring"],
            meta=latest_run_status,
            description=_STAGE_DESCRIPTIONS["monitoring"],
            status=monitoring_status,
            target_page_index=_STAGE_PAGE_INDEX["monitoring"],
        ),
    ]

    actionable = next(
        (stage for stage in stages if stage.status in {"current", "blocked"}),
        stages[-1],
    )
    if all(stage.status == "completed" for stage in stages):
        summary = "当前进度：主路径已闭环完成，可继续进入执行监控查看运行细节。"
        cta_target = _STAGE_PAGE_INDEX["monitoring"]
        cta_label = "查看执行监控"
    else:
        current_label = _STATUS_LABEL[actionable.status]
        summary = (
            f"当前进度：{current_label}位于「{actionable.title}」，"
            f"下一步请进入该阶段完成配置。"
        )
        cta_target = actionable.target_page_index
        cta_label = "继续到下一步"

    return JourneyProjection(
        stages=stages,
        summary=summary,
        cta_label=cta_label,
        cta_target_page_index=cta_target,
    )
