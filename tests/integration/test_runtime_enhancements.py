from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.application.ports import OcrReading
from smartaccess.runtime.domain.run_session import RunSessionStatus, RunStepStatus
from smartaccess.runtime.orchestration.observer import Observer
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowMetadata, WorkflowStep
from smartaccess.shared.events.runtime import RuntimeEventName

DEVICE_ID = "氟基-2236实验室-元能极片电阻仪-01"


def _facade(tmp_path: Path, *, title: str = "ElectroChem Console"):
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id=DEVICE_ID,
        title_contains=title,
        capture_width=800,
        capture_height=600,
        anchors=[
            {
                "id": "status_button",
                "roi": {"x": 10, "y": 10, "width": 80, "height": 32},
                "normalized_roi": {"x": 0.01, "y": 0.01, "width": 0.08, "height": 0.03},
                "observe_roi": {"x": 120, "y": 10, "width": 120, "height": 32},
                "observe_normalized_roi": {
                    "x": 0.12,
                    "y": 0.01,
                    "width": 0.12,
                    "height": 0.03,
                },
                "action_bindings": [{"action": "click", "requires_confirmation": True}],
                "vision_mode": "ocr",
            }
        ],
    )
    return facade


def _workflow(step: WorkflowStep, workflow_id: str = "wf_test") -> WorkflowContract:
    return WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id=workflow_id,
            author="test",
            anchor_profile=DEVICE_ID,
            lifecycle_state="Draft",
        ),
        steps=[step],
    )


def test_observer_matches_normalized_case_and_full_width_text() -> None:
    observer = Observer(vision=object(), confidence_threshold=0.8)
    reading = OcrReading(roi="status", text="　Ｓｔａｔｕｓ：  RUNNING  ", confidence=0.95)

    assert observer.matches(
        reading,
        expected_text="status: running",
        match_mode="contains",
        ignore_case=True,
        normalize_text=True,
    ) is True


def test_observer_rejects_low_confidence_when_threshold_is_required() -> None:
    observer = Observer(vision=object(), confidence_threshold=0.8)
    reading = OcrReading(roi="status", text="Ready", confidence=0.5)

    assert observer.matches(
        reading,
        expected_text="Ready",
        match_mode="equals",
        min_confidence=0.8,
    ) is False


def test_observer_matches_any_expected_candidate() -> None:
    observer = Observer(vision=object())
    reading = OcrReading(roi="status", text="State: completed", confidence=0.9)

    assert observer.matches(
        reading,
        expected_text=["Running", "Completed"],
        match_mode="contains",
        ignore_case=True,
    ) is True


def test_manual_confirmation_blocks_without_running_action_when_rejected(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    events: list[RuntimeEventName] = []
    facade.subscribe(lambda event: events.append(event.name))
    facade.set_confirm_handler(lambda _request: False)
    workflow = _workflow(
        WorkflowStep(
            id="start",
            action="click",
            anchor_id="status_button",
            requires_confirmation=True,
        )
    )

    session = facade.start_run(workflow=workflow, background=False)
    automation = facade.providers()["automation"]

    assert session.status == RunSessionStatus.BLOCKED
    assert session.steps[0].status == RunStepStatus.BLOCKED
    assert RuntimeEventName.RUN_BLOCKED in events
    assert automation.actions == []


def test_window_missing_event_payload_identifies_device_and_window(tmp_path: Path) -> None:
    facade = _facade(tmp_path, title="Missing Application")
    events = []
    facade.subscribe(lambda event: events.append(event))
    workflow = _workflow(
        WorkflowStep(id="start", action="click", anchor_id="status_button"),
        workflow_id="wf_missing_window",
    )

    session = facade.start_run(workflow=workflow, background=False)

    blocked = [event.payload for event in events if event.name == RuntimeEventName.RUN_BLOCKED]
    failed = [event.payload for event in events if event.name == RuntimeEventName.RUN_FAILED]
    assert session.status == RunSessionStatus.FAILED
    assert blocked
    assert blocked[-1]["incident_type"] == "WindowMissing"
    assert blocked[-1]["anchor_profile"] == DEVICE_ID
    assert blocked[-1]["title_contains"] == "Missing Application"
    assert failed[-1]["anchor_profile"] == DEVICE_ID
    assert failed[-1]["title_contains"] == "Missing Application"


def test_runtime_ocr_uses_normalization_and_ignore_case_options(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = _workflow(
        WorkflowStep(
            id="start",
            action="click",
            anchor_id="status_button",
            expected_text="　ＲＵＮＮＩＮＧ　",
            match_mode="equals",
            ignore_case=True,
            normalize_text=True,
            timeout_seconds=1,
        ),
        workflow_id="wf_normalized_ocr",
    )

    session = facade.start_run(workflow=workflow, background=False)

    assert session.status == RunSessionStatus.COMPLETED


def test_runtime_ocr_min_confidence_failure_payload(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    events = []
    facade.subscribe(lambda event: events.append(event))
    workflow = _workflow(
        WorkflowStep(
            id="start",
            action="click",
            anchor_id="status_button",
            expected_text=["Ready", "Running"],
            match_mode="contains",
            min_confidence=0.99,
            timeout_seconds=0,
        ),
        workflow_id="wf_min_confidence_ocr",
    )

    session = facade.start_run(workflow=workflow, background=False)

    failed = [event.payload for event in events if event.name == RuntimeEventName.RUN_FAILED]
    assert session.status == RunSessionStatus.FAILED
    assert failed
    assert failed[-1]["expected_text"] == ["Ready", "Running"]
    assert failed[-1]["min_confidence"] == 0.99
    assert failed[-1]["confidence"] < 0.99
    assert failed[-1]["actual_text"]
