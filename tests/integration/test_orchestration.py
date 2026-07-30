from __future__ import annotations

from datetime import datetime
from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.application.ports import OcrReading
from smartaccess.runtime.domain.run_session import RunSessionStatus, RunStepStatus
from smartaccess.shared.contracts.anchors import ExceptionRule
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

DEVICE_ID = "氟基-2236实验室-元能极片电阻仪-01"


def _workflow(
    workflow_id: str = "wf_test",
    steps: list[dict] | None = None,
) -> WorkflowContract:
    return WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id=workflow_id,
            author="test",
            instrument_profile=DEVICE_ID,
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
        device_id=DEVICE_ID,
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


def _facade_with_dialog_view(tmp_path: Path):
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id=DEVICE_ID,
        title_contains="ElectroChem Console",
        anchors=[],
        capture_width=1000,
        capture_height=800,
        views=[
            {
                "view_id": "main",
                "window_signature": {"title_contains": "ElectroChem Console"},
                "screenshot_size": {"width": 1000, "height": 800},
                "anchors": [
                    {
                        "id": "start_button",
                        "action_region": {
                            "pixel": {"x": 10, "y": 10, "width": 80, "height": 32},
                            "normalized": {
                                "x": 0.01,
                                "y": 0.01,
                                "width": 0.08,
                                "height": 0.03,
                            },
                        },
                        "supported_actions": ["click"],
                    }
                ],
            },
            {
                "view_id": "dialog_reset_done",
                "window_signature": {"title_contains": "Dialog Title"},
                "screenshot_size": {"width": 1000, "height": 800},
                "anchors": [
                    {
                        "id": "reset_done_text",
                        "action_region": {
                            "pixel": {"x": 100, "y": 100, "width": 180, "height": 60},
                            "normalized": {
                                "x": 0.1,
                                "y": 0.1,
                                "width": 0.18,
                                "height": 0.06,
                            },
                        },
                        "observe_region": {
                            "pixel": {"x": 100, "y": 100, "width": 180, "height": 60},
                            "normalized": {
                                "x": 0.1,
                                "y": 0.1,
                                "width": 0.18,
                                "height": 0.06,
                            },
                        },
                        "supported_actions": ["click"],
                    }
                ],
            },
        ],
    )
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


def test_incrementing_type_steps_persist_and_reuse_per_run_value(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = facade.save_workflow(
        _workflow(
            "wf_incrementing_input",
            [
                {
                    "id": "input_1",
                    "action": "type",
                    "target": "anchor_voltage_input",
                    "input_mode": "incrementing",
                    "increment_rule": {},
                    "wait_seconds": 0.0,
                },
                {
                    "id": "input_2",
                    "action": "type",
                    "target": "anchor_voltage_input",
                    "input_mode": "incrementing",
                    "increment_rule": {},
                    "wait_seconds": 0.0,
                },
            ],
        )
    )

    first = facade.start_run(workflow=workflow, background=False)
    first_trace = facade.get_trace(first.session_id)
    second = facade.start_run(workflow=workflow, background=False)
    second_trace = facade.get_trace(second.session_id)

    date = datetime.now().strftime("%Y%m%d")
    assert workflow.steps[0].value is None
    assert first_trace[0].action.value == f"{DEVICE_ID}-test-{date}-001"
    assert first_trace[1].action.value == f"{DEVICE_ID}-test-{date}-001"
    assert second_trace[0].action.value == f"{DEVICE_ID}-test-{date}-002"


def test_incrementing_type_step_resolves_custom_pattern_without_mutating_workflow(
    tmp_path: Path,
) -> None:
    facade = _facade(tmp_path)
    workflow = facade.save_workflow(
        _workflow(
            "wf_custom_increment",
            [
                {
                    "id": "input_sample",
                    "action": "type",
                    "target": "anchor_voltage_input",
                    "input_mode": "incrementing",
                    "increment_rule": {
                        "pattern": "{workflow_id}-{counter:02d}",
                        "start": 7,
                        "width": 2,
                    },
                    "wait_seconds": 0.0,
                },
            ],
        )
    )

    session = facade.start_run(workflow=workflow, background=False)
    trace = facade.get_trace(session.session_id)

    second = facade.start_run(workflow=workflow, background=False)
    second_trace = facade.get_trace(second.session_id)

    assert trace[0].action.value == "wf_custom_increment-07"
    assert second_trace[0].action.value == "wf_custom_increment-08"
    assert workflow.steps[0].value is None
    assert workflow.steps[0].increment_rule is not None
    assert workflow.steps[0].increment_rule.pattern == "{workflow_id}-{counter:02d}"


def test_incrementing_type_step_does_not_advance_after_failed_run(
    tmp_path: Path,
) -> None:
    facade = _facade(tmp_path)
    workflow = facade.save_workflow(
        _workflow(
            "wf_failed_increment",
            [
                {
                    "id": "input_sample",
                    "action": "type",
                    "target": "anchor_voltage_input",
                    "input_mode": "incrementing",
                    "increment_rule": {"pattern": "{counter:03d}"},
                    "match_mode": "contains",
                    "expected_text": "never-matches",
                    "timeout_seconds": 0.1,
                },
            ],
        )
    )

    failed = facade.start_run(workflow=workflow, background=False)
    failed_trace = facade.get_trace(failed.session_id)
    success_workflow = facade.save_workflow(
        _workflow(
            "wf_failed_increment",
            [
                {
                    "id": "input_sample",
                    "action": "type",
                    "target": "anchor_voltage_input",
                    "input_mode": "incrementing",
                    "increment_rule": {"pattern": "{counter:03d}"},
                    "wait_seconds": 0.0,
                },
            ],
        )
    )
    success = facade.start_run(workflow=success_workflow, background=False)
    success_trace = facade.get_trace(success.session_id)

    assert failed.status == RunSessionStatus.FAILED
    assert failed_trace[0].action.value == "001"
    assert success_trace[0].action.value == "001"


def test_incrementing_type_step_cycles_and_formats_date(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = facade.save_workflow(
        _workflow(
            "wf_cycle_increment",
            [
                {
                    "id": "input_sample",
                    "action": "type",
                    "target": "anchor_voltage_input",
                    "input_mode": "incrementing",
                    "increment_rule": {
                        "pattern": "{date}-{counter:02d}",
                        "date_format": "%Y-%m-%d",
                        "start": 100,
                        "min_value": 0,
                        "max_value": 100,
                        "cycle": True,
                    },
                    "wait_seconds": 0.0,
                },
            ],
        )
    )

    first = facade.start_run(workflow=workflow, background=False)
    second = facade.start_run(workflow=workflow, background=False)
    first_trace = facade.get_trace(first.session_id)
    second_trace = facade.get_trace(second.session_id)
    date = datetime.now().strftime("%Y-%m-%d")

    assert first_trace[0].action.value == f"{date}-100"
    assert second_trace[0].action.value == f"{date}-00"


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


def test_wait_step_with_anchor_polls_ocr_without_running_action(tmp_path: Path) -> None:
    facade = _facade_with_dialog_view(tmp_path)
    workflow = facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_wait_for_dialog",
                author="test",
                anchor_profile=DEVICE_ID,
                lifecycle_state="Draft",
            ),
            steps=[
                WorkflowStep(
                    id="wait_for_reset_done",
                    action="wait",
                    view_id="dialog_reset_done",
                    anchor_id="reset_done_text",
                    expected_text="复位结束",
                    match_mode="contains",
                    timeout_seconds=1,
                )
            ],
        )
    )

    facade._orchestrator._observer._vision.read_roi_text = lambda **_kwargs: OcrReading(
        roi="reset_done_text",
        text="复位结束",
        confidence=0.96,
    )
    session = facade.start_run(workflow=workflow, background=False)
    trace = facade.get_trace(session.session_id)
    automation = facade.providers()["automation"]

    assert session.status == RunSessionStatus.COMPLETED
    assert automation.actions == []
    assert trace[0].action.type == "wait"
    assert trace[0].view_id == "dialog_reset_done"
    assert trace[0].anchor_id == "reset_done_text"
    assert trace[0].wait_strategy.type == "ocr_poll"
    assert trace[0].actual_text == "复位结束"
    assert trace[0].matched is True
    assert trace[0].screenshot_path


def test_multiview_runtime_keeps_main_window_as_execution_target(tmp_path: Path) -> None:
    facade = _facade_with_dialog_view(tmp_path)
    workflow = facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_dialog_view_click",
                author="test",
                anchor_profile=DEVICE_ID,
                lifecycle_state="Draft",
            ),
            steps=[
                WorkflowStep(
                    id="click_dialog_anchor",
                    action="click",
                    view_id="dialog_reset_done",
                    anchor_id="reset_done_text",
                    match_mode="none",
                    wait_seconds=0.0,
                )
            ],
        )
    )

    session = facade.start_run(workflow=workflow, background=False)
    automation = facade.providers()["automation"]

    assert session.status == RunSessionStatus.COMPLETED
    assert automation.actions == [("click", "reset_done_text", None)]


def test_exception_popup_rule_blocks_run_before_action(tmp_path: Path) -> None:
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    profile = facade.create_calibration(
        device_id=DEVICE_ID,
        title_contains="ElectroChem Console",
        anchors=[],
        capture_width=1000,
        capture_height=800,
        views=[
            {
                "view_id": "main",
                "window_signature": {"title_contains": "ElectroChem Console"},
                "anchors": [
                    {
                        "id": "start_button",
                        "action_region": {
                            "pixel": {"x": 10, "y": 10, "width": 80, "height": 32},
                            "normalized": {
                                "x": 0.01,
                                "y": 0.01,
                                "width": 0.08,
                                "height": 0.03,
                            },
                        },
                        "supported_actions": ["click"],
                    }
                ],
            },
            {
                "view_id": "dialog_connection_failed",
                "window_signature": {"title_contains": "ElectroChem Console"},
                "anchors": [
                    {
                        "id": "connection_failed_text",
                        "action_region": {
                            "pixel": {"x": 100, "y": 100, "width": 200, "height": 80},
                            "normalized": {
                                "x": 0.1,
                                "y": 0.1,
                                "width": 0.2,
                                "height": 0.08,
                            },
                        },
                        "observe_region": {
                            "pixel": {"x": 100, "y": 100, "width": 200, "height": 80},
                            "normalized": {
                                "x": 0.1,
                                "y": 0.1,
                                "width": 0.2,
                                "height": 0.08,
                            },
                        },
                        "supported_actions": ["click"],
                    }
                ],
            },
        ],
    )
    profile.exception_rules = [
        ExceptionRule(
            id="connection_failed",
            view_id="dialog_connection_failed",
            anchor_id="connection_failed_text",
            expected_text="连接失败",
            match_mode="contains",
            blocking=True,
            message="设备连接失败，请人工处理",
        )
    ]
    facade.save_instrument(profile)
    workflow = facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_exception_popup",
                author="test",
                anchor_profile=DEVICE_ID,
                lifecycle_state="Draft",
            ),
            steps=[WorkflowStep(id="start", action="click", anchor_id="start_button")],
        )
    )
    events = []
    facade.subscribe(lambda event: events.append(event))
    facade._orchestrator._observer._vision.read_roi_text = lambda **_kwargs: OcrReading(
        roi="connection_failed_text",
        text="设备连接失败",
        confidence=0.97,
    )

    session = facade.start_run(workflow=workflow, background=False)
    automation = facade.providers()["automation"]
    blocked = [event.payload for event in events if event.name == RuntimeEventName.RUN_BLOCKED]

    assert session.status == RunSessionStatus.BLOCKED
    assert session.steps[0].status == RunStepStatus.BLOCKED
    assert automation.actions == []
    assert len(blocked) == 1
    assert blocked[-1]["incident_type"] == "DevicePopup"
    assert blocked[-1]["exception_rule_id"] == "connection_failed"
    assert blocked[-1]["actual_text"] == "设备连接失败"
    assert blocked[-1]["view_id"] == "dialog_connection_failed"
