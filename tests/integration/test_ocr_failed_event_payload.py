from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowStep,
)
from smartaccess.shared.events.runtime import RuntimeEventName


def _facade(tmp_path: Path):
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        capture_width=800,
        capture_height=600,
        anchors=[
            {
                "id": "status_button",
                "roi": {"x": 10, "y": 10, "width": 80, "height": 32},
                "normalized_roi": {
                    "x": 0.01,
                    "y": 0.01,
                    "width": 0.08,
                    "height": 0.03,
                },
                "observe_roi": {"x": 120, "y": 10, "width": 120, "height": 32},
                "observe_normalized_roi": {
                    "x": 0.12,
                    "y": 0.01,
                    "width": 0.12,
                    "height": 0.03,
                },
                "action_bindings": [{"action": "click"}],
                "vision_mode": "ocr",
            }
        ],
    )
    return facade


def test_ocr_mismatch_failed_event_includes_debug_payload(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    events = []
    facade.subscribe(lambda event: events.append(event))
    workflow = facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_ocr_mismatch",
                author="test",
                anchor_profile="d1",
                lifecycle_state="Draft",
            ),
            steps=[
                WorkflowStep(
                    id="step_4",
                    action="click",
                    anchor_id="status_button",
                    expected_text="肖旭",
                    match_mode="contains",
                    timeout_seconds=0,
                )
            ],
        )
    )

    session = facade.start_run(workflow=workflow, background=False)

    failed = [
        event.payload
        for event in events
        if event.name == RuntimeEventName.RUN_FAILED
    ]
    assert session.status.value == "failed"
    assert failed
    payload = failed[-1]
    assert payload["step_id"] == "step_4"
    assert payload["detail"] == "OCR 结果未满足期望"
    assert payload["match_mode"] == "contains"
    assert payload["expected_text"] == "肖旭"
    assert payload["actual_text"]
    assert payload["matched"] is False
    assert payload["attempts"] >= 1
    assert payload["wait_strategy"]["type"] == "ocr_poll"
