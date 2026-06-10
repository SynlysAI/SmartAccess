from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.domain.run_session import RunSessionStatus, RunStepStatus
from smartaccess.shared.config.settings import AppSettings
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
        roi_bindings={"voltage_panel": "roi_voltage_value"},
        steps=[WorkflowStep(**s) for s in (steps or [
            {"id": "input_target_voltage", "action": "type", "target": "anchor_voltage_input", "value": "4.20"},
        ])],
        outputs=[WorkflowOutput(key="final_voltage", source="roi_voltage_value")],
        retry_policy=WorkflowRetryPolicy(max_attempts=2),
    )


def _facade(tmp_path: Path):
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[
            {"id": "anchor_voltage_input", "type": "input", "vision_mode": "none"},
            {"id": "roi_voltage_value", "type": "observation", "vision_mode": "ocr"},
        ],
        actions=["type", "wait_until"],
        safety_limits={"max_voltage": 5.0, "min_voltage": 0.0},
    )
    facade.register_workflow(_workflow())
    return facade


def test_full_run_completes_and_writes_trace(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    events: list[RuntimeEventName] = []
    facade.subscribe(lambda e: events.append(e.name))

    workflow = facade.list_workflows()[0]
    session = facade.start_run(workflow=workflow)

    assert session.status == RunSessionStatus.COMPLETED
    assert RuntimeEventName.RUN_COMPLETED in events
    # One trace record per workflow step.
    trace = facade.get_trace(session.session_id)
    assert len(trace) == len(workflow.steps)
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

    workflow = facade.list_workflows()[0]
    session = facade.start_run(workflow=workflow)

    assert session.status == RunSessionStatus.COMPLETED
    assert RuntimeEventName.RUN_RECOVERED in events


def test_wait_until_missing_condition_fails_without_crashing(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = facade.register_workflow(_workflow(
        "wf_missing_condition",
        [{"id": "wait_for_status", "action": "wait_until", "target": "roi_voltage_value"}],
    ))

    session = facade.start_run(workflow=workflow)

    assert session.status == RunSessionStatus.FAILED
    assert session.steps[0].status == RunStepStatus.FAILED


def test_observation_exception_fails_run_without_thread_crash(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    events: list[tuple[RuntimeEventName, dict]] = []
    facade.subscribe(lambda e: events.append((e.name, e.payload)))

    workflow = facade.register_workflow(_workflow(
        "wf_observation_boom",
        [
            {
                "id": "wait_for_status",
                "action": "wait_until",
                "target": "roi_voltage_value",
                "condition": {
                    "source": "voltage_panel",
                    "operator": "not_empty",
                    "timeout_seconds": 1,
                    "poll_interval_seconds": 0.1,
                },
            }
        ],
    ))

    def boom(*args, **kwargs):
        raise RuntimeError("OCR init failed")

    facade._orchestrator._observer._vision.read_roi_text = boom
    session = facade.start_run(workflow=workflow)

    assert session.status == RunSessionStatus.FAILED
    assert session.steps[0].status == RunStepStatus.FAILED
    failed_payloads = [payload for name, payload in events if name == RuntimeEventName.RUN_FAILED]
    assert any("OCR init failed" in str(payload.get("detail")) for payload in failed_payloads)


def test_safety_violation_blocks_run(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = facade.register_workflow(_workflow(
        "wf_unsafe",
        [{"id": "input_target_voltage", "action": "type", "target": "anchor_voltage_input", "value": "9.99"}],
    ))
    session = facade.start_run(workflow=workflow)
    assert session.status == RunSessionStatus.FAILED
