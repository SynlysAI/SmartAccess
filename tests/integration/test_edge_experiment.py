from __future__ import annotations

import pytest

from smartaccess.runtime.adapters.inmemory import (
    EchoInstructionGenerator,
    StubProcessExecutorClient,
)
from smartaccess.runtime.application.experiment_service import ExperimentService
from smartaccess.runtime.domain.experiment import NotReadyToExecuteError
from smartaccess.shared.contracts.edge_api import ExecuteRequest, TriggerGenerateRequest


def _service() -> ExperimentService:
    return ExperimentService(
        instruction_generator=EchoInstructionGenerator(),
        executor_client=StubProcessExecutorClient(),
        udp_target={"host": "127.0.0.1", "port": 8889},
    )


def test_trigger_then_execute_then_status() -> None:
    service = _service()

    triggered = service.trigger(
        TriggerGenerateRequest(experiment_plan="S 1 open\nS 2 run")
    )
    assert triggered.ok
    assert triggered.signal == "TRIGGER_GENERATE_LOCAL"
    assert triggered.instructions == ["S 1 open", "S 2 run"]
    assert triggered.request_id

    executed = service.execute(ExecuteRequest())
    assert executed.ok
    assert executed.signal == "EXECUTE_PROCESS_FILE"
    assert executed.udp_ack == {"ok": True, "echo": "EXECUTE_PROCESS_FILE"}

    status = service.status()
    assert status.ok
    assert status.status == "success"
    assert status.last_triggered_at is not None


def test_execute_before_trigger_is_rejected() -> None:
    with pytest.raises(NotReadyToExecuteError):
        _service().execute(ExecuteRequest())


def test_explicit_request_id_is_preserved() -> None:
    triggered = _service().trigger(
        TriggerGenerateRequest(experiment_plan="S 1 open", request_id="req-123")
    )
    assert triggered.request_id == "req-123"


def test_health_reports_udp_target() -> None:
    health = _service().health()
    assert health.ok
    assert health.service == "smartaccess-edge"
    assert health.udp_target == {"host": "127.0.0.1", "port": 8889}


def test_edge_app_registers_mvp_routes() -> None:
    pytest.importorskip("fastapi")
    from smartaccess.bootstrap import build_edge_app

    app = build_edge_app()
    paths = {route.path for route in app.routes}
    assert {
        "/health",
        "/api/v1/experiment/trigger",
        "/api/v1/experiment/execute",
        "/api/v1/experiment/status",
    } <= paths


def test_edge_app_serves_health_over_http() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from smartaccess.bootstrap import build_edge_app

    with TestClient(build_edge_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["service"] == "smartaccess-edge"
