from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.application.ports import OcrReading
from smartaccess.runtime.domain.run_session import RunSessionStatus, RunStepStatus
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.contracts.anchors import SafetyLimits
from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowRetryPolicy,
    WorkflowStep,
)
from smartaccess.shared.events import RuntimeEventName


def _workflow(
    workflow_id: str = "wf_test",
    steps: list[dict] | None = None,
) -> WorkflowContract:
    return WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id=workflow_id,
            author="test",
            instrument_profile="d1",
            experiment_type="smoke_test",
            lifecycle_state="Draft",
        ),
        roi_bindings={"voltage_panel": "anchor_voltage_input"},
        steps=[WorkflowStep(**s) for s in (steps or [
            {"id": "input_target_voltage", "action": "type", "target": "anchor_voltage_input", "value": "4.20"},
        ])],
        outputs=[WorkflowOutput(key="final_voltage", source="anchor_voltage_input")],
        retry_policy=WorkflowRetryPolicy(max_attempts=2),
    )


def _facade(tmp_path: Path):
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    profile = facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[
            {
                "id": "anchor_voltage_input",
                "roi": {"x": 10, "y": 10, "width": 80, "height": 32},
                "normalized_roi": {"x": 0.01, "y": 0.01, "width": 0.08, "height": 0.03},
                "observe_roi": {"x": 120, "y": 10, "width": 120, "height": 32},
                "observe_normalized_roi": {"x": 0.12, "y": 0.01, "width": 0.12, "height": 0.03},
                "action_bindings": [{"action": "type"}],
                "vision_mode": "ocr",
            },
        ],
        capture_width=1000,
        capture_height=800,
    )
    profile.safety_limits = SafetyLimits(max_voltage=5.0, min_voltage=0.0)
    facade.save_instrument(profile)
    facade.save_workflow(_workflow())
    return facade


def test_full_run_completes_and_writes_trace(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    events: list[RuntimeEventName] = []
    facade.subscribe(lambda e: events.append(e.name))

    workflow = facade.list_workflows()[0]
    session = facade.start_run(workflow=workflow, background=False)

    assert session.status == RunSessionStatus.COMPLETED
    assert RuntimeEventName.RUN_COMPLETED in events
    # One trace record per workflow step.
    trace = facade.get_trace(session.session_id)
    assert len(trace) == len(workflow.steps)
    assert trace[0].wait_strategy.type == "fixed_wait"
    assert trace[0].matched is None
    assert trace[0].actual_text is None
    assert all(step.status == RunStepStatus.SUCCEEDED for step in session.steps)

    # run_trace.jsonl is persisted under the workspace.
    trace_file = tmp_path / "runs" / session.session_id / "run_trace.jsonl"
    assert trace_file.exists()
    assert trace_file.read_text(encoding="utf-8").strip()


def test_low_confidence_triggers_recovery(tmp_path: Path) -> None:
    # The default stub vision provider returns low confidence on first read,
    # so the run must recover (retry) at least once and still complete.
    facade = _facade(tmp_path)
    events: list[RuntimeEventName] = []
    facade.subscribe(lambda e: events.append(e.name))

    workflow = facade.save_workflow(_workflow(
        "wf_low_confidence_ocr",
        [
            {
                "id": "wait_for_voltage",
                "action": "type",
                "target": "anchor_voltage_input",
                "value": "4.20",
                "expected_text": "4.20",
                "match_mode": "contains",
                "timeout_seconds": 2,
            }
        ],
    ))

    readings = [
        OcrReading(roi="anchor_voltage_input", text="", confidence=0.45),
        OcrReading(roi="anchor_voltage_input", text="4.20", confidence=0.95),
    ]

    def read_roi_text(*args, **kwargs):
        """返回一次低置信度未命中读数，再返回匹配读数。"""

        return readings.pop(0)

    facade._orchestrator._observer._vision.read_roi_text = read_roi_text
    session = facade.start_run(workflow=workflow, background=False)

    assert session.status == RunSessionStatus.COMPLETED
    assert RuntimeEventName.RUN_RECOVERED in events


def test_action_without_ocr_condition_uses_fixed_wait(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = facade.save_workflow(_workflow(
        "wf_fixed_wait",
        [{"id": "focus_voltage", "action": "click", "target": "anchor_voltage_input", "wait_seconds": 0.0}],
    ))

    session = facade.start_run(workflow=workflow, background=False)
    trace = facade.get_trace(session.session_id)

    assert session.status == RunSessionStatus.COMPLETED
    assert session.steps[0].status == RunStepStatus.SUCCEEDED
    assert trace[0].wait_strategy.type == "fixed_wait"
    assert trace[0].matched is None


def test_observation_exception_fails_run_without_thread_crash(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    events: list[tuple[RuntimeEventName, dict]] = []
    facade.subscribe(lambda e: events.append((e.name, e.payload)))

    workflow = facade.save_workflow(_workflow(
        "wf_observation_boom",
        [
            {
                "id": "wait_for_status",
                "action": "click",
                "target": "anchor_voltage_input",
                "match_mode": "not_empty",
                "timeout_seconds": 1,
            }
        ],
    ))

    def boom(*args, **kwargs):
        raise RuntimeError("OCR init failed")

    facade._orchestrator._observer._vision.read_roi_text = boom
    session = facade.start_run(workflow=workflow, background=False)

    assert session.status == RunSessionStatus.FAILED
    assert session.steps[0].status == RunStepStatus.FAILED
    failed_payloads = [payload for name, payload in events if name == RuntimeEventName.RUN_FAILED]
    assert any("OCR init failed" in str(payload.get("detail")) for payload in failed_payloads)


def test_ocr_trace_records_expected_actual_and_match(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = facade.save_workflow(_workflow(
        "wf_ocr_trace",
        [
            {
                "id": "wait_for_text",
                "action": "type",
                "target": "anchor_voltage_input",
                "value": "4.20",
                "expected_text": "4.20",
                "match_mode": "contains",
                "wait_seconds": 0.1,
                "timeout_seconds": 2,
            }
        ],
    ))

    session = facade.start_run(workflow=workflow, background=False)
    trace = facade.get_trace(session.session_id)

    assert session.status == RunSessionStatus.COMPLETED
    assert trace[0].expected_text == "4.20"
    assert trace[0].actual_text
    assert trace[0].match_mode == "contains"
    assert trace[0].matched is True
    assert trace[0].attempts >= 1
    assert trace[0].wait_strategy.type == "ocr_poll"
    assert trace[0].wait_strategy.wait_seconds == 0.1
    assert trace[0].elapsed_seconds >= 0.1
    assert trace[0].screenshot_path


def test_safety_violation_blocks_run(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = facade.save_workflow(_workflow(
        "wf_unsafe",
        [{"id": "input_target_voltage", "action": "type", "target": "anchor_voltage_input", "value": "9.99"}],
    ))
    session = facade.start_run(workflow=workflow, background=False)
    assert session.status == RunSessionStatus.FAILED
