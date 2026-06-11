from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.domain.run_session import RunSessionStatus
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.contracts.workflow import (
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowRetryPolicy,
    WorkflowStep,
)


def _demo_workflow(workflow_id: str = "wf_test") -> WorkflowContract:
    return WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id=workflow_id,
            author="test",
            instrument_profile="d1",
            experiment_type="smoke_test",
            lifecycle_state="Draft",
        ),
        roi_bindings={"status_banner": "status_button"},
        steps=[WorkflowStep(
            id="start_and_wait",
            action="click",
            anchor_id="status_button",
            expected_text="Running",
            match_mode="contains",
            timeout_seconds=5.0,
        )],
        outputs=[WorkflowOutput(key="run_status", source="status_button")],
        retry_policy=WorkflowRetryPolicy(max_attempts=2),
    )


def test_facade_smoke_and_dashboard(tmp_path: Path) -> None:
    facade = build_runtime_facade(
        AppSettings(workspace_dir=tmp_path),
        eval_cases_dir=Path(__file__).resolve().parents[2] / "ai/harness/evals/cases",
    )

    received = []
    facade.subscribe(lambda e: received.append(e.name.value))

    facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[
            {
                "id": "status_button",
                "roi": {"x": 10, "y": 10, "width": 80, "height": 32},
                "normalized_roi": {"x": 0.01, "y": 0.01, "width": 0.08, "height": 0.03},
                "observe_roi": {"x": 120, "y": 10, "width": 120, "height": 32},
                "observe_normalized_roi": {"x": 0.12, "y": 0.01, "width": 0.12, "height": 0.03},
                "vision_mode": "ocr",
            }
        ],
        actions=["click"],
        safety_limits={},
    )
    workflow = facade.register_workflow(_demo_workflow())

    session = facade.start_run(workflow=workflow)
    assert session.status == RunSessionStatus.COMPLETED
    assert "run.completed" in received

    dashboard = facade.dashboard()
    assert dashboard.devices
    assert any(r.session_id == session.session_id for r in dashboard.recent_runs)

    evals = facade.run_evals()
    scenario_ids = {result.scenario_id for result in evals}
    assert len(evals) == 7
    assert {"serial_udp_debug_assistant", "windows_calculator_ocr"} <= scenario_ids


def test_facade_updates_workflow_bindings_and_outputs(tmp_path: Path) -> None:
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    workflow = facade.register_workflow(_demo_workflow())
    updated = workflow.model_copy(deep=True)
    updated.roi_bindings = {"contact_result": "contact_item"}
    updated.outputs = [WorkflowOutput(key="selected_contact", source="contact_item")]

    saved = facade.update_workflow(updated)

    assert saved.roi_bindings == {"contact_result": "contact_item"}
    assert [(out.key, out.source) for out in saved.outputs] == [("selected_contact", "contact_item")]
    assert facade.list_workflows()[0].roi_bindings == {"contact_result": "contact_item"}
    assert facade.standardize(saved).ok
