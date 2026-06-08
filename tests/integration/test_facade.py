from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.runtime.domain.run_session import RunSessionStatus
from smartaccess.shared.config.settings import AppSettings


def test_facade_smoke_and_dashboard(tmp_path: Path) -> None:
    facade = build_runtime_facade(
        AppSettings(workspace_dir=tmp_path),
        seed_demo=True,
        eval_cases_dir=Path(__file__).resolve().parents[2] / "ai/harness/evals/cases",
    )

    received = []
    facade.subscribe(lambda e: received.append(e.name.value))

    # Seed produced one instrument + one workflow.
    assert facade.list_instruments()
    workflow = facade.list_workflows()[0]

    session = facade.start_run(workflow=workflow)
    assert session.status == RunSessionStatus.COMPLETED
    assert "run.completed" in received

    dashboard = facade.dashboard()
    assert dashboard.devices
    assert any(r.session_id == session.session_id for r in dashboard.recent_runs)

    evals = facade.run_evals()
    assert len(evals) == 5
