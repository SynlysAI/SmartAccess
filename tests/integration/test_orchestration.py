from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.domain.run_session import RunSessionStatus, RunStepStatus
from smartaccess.shared.config.settings import AppSettings
from smartaccess.shared.events import RuntimeEventName


def _facade(tmp_path: Path):
    return build_runtime_facade(AppSettings(workspace_dir=tmp_path), seed_demo=True)


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


def test_safety_violation_blocks_run(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    # A workflow that types a voltage above the instrument's 5.0V limit.
    workflow = facade.generate_workflow(
        "set an unsafe voltage",
        {
            "workflow_id": "wf_unsafe",
            "instrument_profile": "potentiostat_win_01",
            "steps": [
                {"id": "input_target_voltage", "action": "type", "target": "anchor_voltage_input", "value": "9.99"},
            ],
            "roi_bindings": {"voltage_panel": "roi_voltage_value"},
        },
    )
    session = facade.start_run(workflow=workflow)
    assert session.status == RunSessionStatus.FAILED
