from __future__ import annotations

from pathlib import Path

import pytest

from smartaccess.runtime.adapters.ai_stub import TemplatePromptWorkflowGenerator
from smartaccess.runtime.adapters.automation_stub import StubAutomationProvider
from smartaccess.runtime.adapters.deepseek_instrument_generator import DeepSeekInstrumentProfileGenerator
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
from smartaccess.shared.contracts.anchors import AnchorsContract
from smartaccess.shared.contracts.io import dump_yaml_contract, load_yaml_contract
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowOutput
from smartaccess.shared.events import EventBus, RuntimeEventName

REPO_ROOT = Path(__file__).resolve().parents[2]


def _draft(workspace: Path) -> WorkflowService:
    return WorkflowService(
        draft_generator=TemplatePromptWorkflowGenerator(),
        workspace_dir=workspace,
    )


def test_calibration_writes_profile(tmp_path: Path) -> None:
    cal = CalibrationService(automation=StubAutomationProvider(), workspace_dir=tmp_path)
    profile = cal.create_profile(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[{"id": "status_button", "main_action": "click"}],
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

    svc.transition(workflow, WorkflowLifecycleState.CALIBRATED)
    with pytest.raises(ValueError):
        svc.transition(workflow, WorkflowLifecycleState.PUBLISHED)


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


def test_deepseek_instrument_generator_normalizes_legacy_anchor_shape() -> None:
    raw = {
        "device_id": "weixin_01",
        "window_signature": {"title_contains": "微信", "capture_width": 1000, "capture_height": 800},
        "anchors": [
            {
                "id": "search_bar",
                "roi": {"x": 10, "y": 20, "width": 120, "height": 30},
                "normalized_roi": {"x": 0.01, "y": 0.025, "width": 0.12, "height": 0.0375},
                "action_bindings": [{"action": "click", "requires_confirmation": False}],
                "vision_mode": "none",
            }
        ],
    }

    normalized = DeepSeekInstrumentProfileGenerator._normalize_anchor_profile(
        raw,
        {"device_id": "weixin_01", "title_contains": "微信"},
    )
    profile = AnchorsContract.model_validate(normalized)

    assert profile.profile_id == "weixin_01"
    assert profile.anchors[0].id == "search_bar"
    assert profile.anchors[0].action_region.pixel.width == 120
    assert profile.anchors[0].supported_actions == ["click"]


def test_deepseek_instrument_generator_friendly_validation_error() -> None:
    try:
        AnchorsContract.model_validate({"profile_id": "bad", "anchors": [{}]})
    except Exception as exc:
        message = DeepSeekInstrumentProfileGenerator._friendly_validation_error(exc)
    else:  # pragma: no cover - defensive
        message = ""

    assert "pydantic.dev" not in message
    assert "input_value" not in message
    assert "缺少字段" in message


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
        platform=StubPlatformClient(offline=True),
        event_bus=bus,
        max_attempts=2,
    )
    sync.enqueue("status", {"run": "s1"})

    assert sync.sync().pending == 1
    stats = sync.sync()
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


def test_evaluation_loads_seven_key_cases() -> None:
    svc = EvaluationService(cases_dir=REPO_ROOT / "ai/harness/evals/cases")
    results = svc.run_all()
    assert len(results) == 7
    assert all(r.passed for r in results)


@pytest.mark.parametrize(
    ("example_dir", "workflow_id", "ocr_step_id", "expected_text"),
    [
        (
            "serial_debug_assistant_udp",
            "wf_serial_debug_assistant_udp_send",
            "send_udp_payload",
            "SmartAccess UDP validation",
        ),
        (
            "windows_calculator",
            "wf_windows_calculator_12_plus_34",
            "verify_result_46",
            "46",
        ),
    ],
)
def test_capability_example_assets_are_standardized(
    tmp_path: Path,
    example_dir: str,
    workflow_id: str,
    ocr_step_id: str,
    expected_text: str,
) -> None:
    base = REPO_ROOT / "docs/contracts/examples" / example_dir
    profile = load_yaml_contract(base / "anchors.yaml", AnchorsContract)
    workflow = load_yaml_contract(base / "workflow.yaml", WorkflowContract)

    assert workflow.metadata.workflow_id == workflow_id
    assert workflow.metadata.anchor_profile == profile.profile_id

    dump_yaml_contract(profile, tmp_path / "anchors" / profile.profile_id / "anchors.yaml")
    svc = WorkflowService(draft_generator=None, workspace_dir=tmp_path)
    check = svc.standardize_check(workflow)
    assert check.ok, check.issues

    ocr_step = next(step for step in workflow.steps if step.id == ocr_step_id)
    anchor = profile.anchor_map()[ocr_step.anchor_id]
    assert ocr_step.expected_text == expected_text
    assert ocr_step.match_mode == "contains"
    assert anchor.observe_region is not None
