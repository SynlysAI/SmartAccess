from __future__ import annotations

from pathlib import Path

import pytest

from smartaccess.runtime.adapters.automation_stub import StubAutomationProvider
from smartaccess.runtime.adapters.ai_stub import TemplatePromptWorkflowGenerator
from smartaccess.runtime.adapters.platform_stub import StubPlatformClient
from smartaccess.runtime.application.calibration_service import CalibrationService
from smartaccess.runtime.application.evaluation_service import EvaluationService
from smartaccess.runtime.application.incident_service import IncidentService
from smartaccess.runtime.application.platform_sync_service import PlatformSyncService
from smartaccess.runtime.application.template_service import TemplateService
from smartaccess.runtime.application.workflow_service import WorkflowService
from smartaccess.runtime.domain.incident import IncidentType
from smartaccess.runtime.domain.instrument import InstrumentStatus
from smartaccess.runtime.domain.template import TemplateVersionStatus
from smartaccess.runtime.domain.workflow import WorkflowLifecycleState
from smartaccess.shared.contracts.instrument_profile import InstrumentProfileContract
from smartaccess.shared.contracts.io import load_yaml_contract
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowOutput
from smartaccess.shared.events import EventBus, RuntimeEventName

REPO_ROOT = Path(__file__).resolve().parents[2]


def _draft(workspace) -> WorkflowService:
    return WorkflowService(
        draft_generator=TemplatePromptWorkflowGenerator(), workspace_dir=workspace
    )


def test_calibration_writes_profile(tmp_path: Path) -> None:
    cal = CalibrationService(automation=StubAutomationProvider(), workspace_dir=tmp_path)
    profile = cal.create_profile(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[{"id": "roi_status", "type": "roi"}],
        safety_limits={"max_voltage": 5.0},
    )
    cal.activate("d1")
    assert (tmp_path / "instruments" / "d1" / "instrument_profile.yaml").exists()
    assert profile.device_id == "d1"
    assert cal.status_of("d1") == InstrumentStatus.ACTIVE


def test_workflow_standardize_and_transition_guard(tmp_path: Path) -> None:
    svc = _draft(tmp_path)
    workflow = svc.draft_from_prompt("x", {"workflow_id": "w1", "instrument_profile": "d1"})
    assert svc.standardize_check(workflow).ok

    svc.transition(workflow, WorkflowLifecycleState.CALIBRATED)  # Draft -> Calibrated ok
    with pytest.raises(ValueError):
        svc.transition(workflow, WorkflowLifecycleState.PUBLISHED)  # illegal jump


def test_workflow_update_persists_bindings_and_outputs(tmp_path: Path) -> None:
    svc = _draft(tmp_path)
    workflow = svc.draft_from_prompt("x", {"workflow_id": "w1", "instrument_profile": "d1"})
    workflow.roi_bindings = {"contact_result": "contact_item"}
    workflow.outputs = [WorkflowOutput(key="selected_contact", source="contact_item")]

    svc.update(workflow)

    reloaded = _draft(tmp_path).get("w1")
    assert reloaded is not None
    assert reloaded.roi_bindings == {"contact_result": "contact_item"}
    assert [(out.key, out.source) for out in reloaded.outputs] == [("selected_contact", "contact_item")]
    assert svc.standardize_check(workflow).ok


def test_template_publish_supersede_and_rollback(tmp_path: Path) -> None:
    bus = EventBus()
    svc = TemplateService(platform=StubPlatformClient(), workspace_dir=tmp_path, event_bus=bus)
    drafts = _draft(tmp_path)

    v1 = drafts.draft_from_prompt("x", {"workflow_id": "w1", "instrument_profile": "d1"})
    v1.metadata.template_id = "t1"
    v1.metadata.template_version = "1.0.0"
    svc.publish(v1)

    v2 = v1.model_copy(deep=True)
    v2.metadata.template_version = "1.1.0"
    svc.publish(v2)

    versions = {r.identity.template_version: r.status for r in svc.list_versions("t1")}
    assert versions["1.0.0"] == TemplateVersionStatus.SUPERSEDED
    assert versions["1.1.0"] == TemplateVersionStatus.PUBLISHED

    svc.rollback("t1", "1.0.0")
    versions = {r.identity.template_version: r.status for r in svc.list_versions("t1")}
    assert versions["1.0.0"] == TemplateVersionStatus.PUBLISHED
    assert versions["1.1.0"] == TemplateVersionStatus.ROLLED_BACK


def test_platform_outbox_retries_then_fails() -> None:
    bus = EventBus()
    failures: list[RuntimeEventName] = []
    bus.subscribe(lambda e: failures.append(e.name))
    sync = PlatformSyncService(
        platform=StubPlatformClient(offline=True), event_bus=bus, max_attempts=2
    )
    sync.enqueue("status", {"run": "s1"})

    assert sync.sync().pending == 1  # first failure -> requeued
    stats = sync.sync()  # second failure -> dropped to failed
    assert stats.pending == 0
    assert stats.failed == 1
    assert RuntimeEventName.PLATFORM_SYNC_FAILED in failures


def test_incident_manual_confirm_flow() -> None:
    bus = EventBus()
    seen: list[RuntimeEventName] = []
    bus.subscribe(lambda e: seen.append(e.name))
    svc = IncidentService(event_bus=bus)

    incident = svc.open(
        session_id="s1",
        step_id="start_run",
        incident_type=IncidentType.SAFETY_LIMIT_VIOLATION,
        detail="参数越界",
    )
    assert incident.requires_manual_confirm
    assert RuntimeEventName.RUN_BLOCKED in seen

    svc.confirm(incident.incident_id)
    assert incident.resolved
    assert RuntimeEventName.RUN_RECOVERED in seen


def test_evaluation_loads_five_key_cases() -> None:
    svc = EvaluationService(cases_dir=REPO_ROOT / "ai/harness/evals/cases")
    results = svc.run_all()
    assert len(results) == 5
    assert all(r.passed for r in results)


def test_wechat_demo_assets_are_standardized() -> None:
    profile = load_yaml_contract(
        REPO_ROOT / "workspace/instruments/weixin_01/instrument_profile.yaml",
        InstrumentProfileContract,
    )
    anchor_modes = {anchor.id: anchor.vision_mode for anchor in profile.anchors}
    anchor_configs = {anchor.id: anchor.vision_config for anchor in profile.anchors}
    assert anchor_modes["用户确认"] == "ocr"
    assert anchor_modes["联系人头像模板"] == "template"
    assert anchor_modes["会话存在"] == "presence"
    assert anchor_configs["会话存在"].presence_threshold == pytest.approx(0.01)
    assert anchor_modes["发送按钮颜色"] == "color"

    workflow_paths = [
        REPO_ROOT / "workspace/workflows/wf_wechat_basic_actions/draft.yaml",
        REPO_ROOT / "workspace/workflows/wf_wechat_ocr_wait/draft.yaml",
        REPO_ROOT / "workspace/workflows/wf_wechat_template_match/draft.yaml",
        REPO_ROOT / "workspace/workflows/wf_wechat_color_presence/draft.yaml",
        REPO_ROOT / "workspace/workflows/wf_wechat_screenshot_check/draft.yaml",
        REPO_ROOT / "workspace/templates/wf_wechat_send_test_standard/1.0.1/workflow.yaml",
    ]
    svc = WorkflowService(draft_generator=None, workspace_dir=REPO_ROOT / "workspace")
    for path in workflow_paths:
        workflow = load_yaml_contract(path, WorkflowContract)
        assert workflow.metadata.instrument_profile == "weixin_01"
        assert svc.standardize_check(workflow).ok, workflow.metadata.workflow_id
