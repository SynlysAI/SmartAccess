from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QTableWidgetItem  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.shared.config.settings import AppSettings  # noqa: E402
from smartaccess.shared.contracts.workflow import (  # noqa: E402
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowStep,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _facade(tmp_path: Path):
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[{"id": "roi_status", "type": "observation", "vision_mode": "ocr"}],
        actions=["wait_until"],
        safety_limits={},
    )
    facade.register_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_test",
                author="test",
                instrument_profile="d1",
                experiment_type="smoke_test",
                lifecycle_state="Draft",
            ),
            roi_bindings={"status_banner": "roi_status"},
            steps=[WorkflowStep(id="wait_running", action="wait_until", target="roi_status")],
            outputs=[WorkflowOutput(key="run_status", source="roi_status")],
        )
    )
    return facade


def test_main_window_builds_and_navigates(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.shell.main_window import MainWindow

    facade = _facade(tmp_path)
    window = MainWindow(facade)

    assert window._stack.count() == 5
    for row in range(5):
        window._nav.setCurrentRow(row)
        assert window._stack.currentIndex() == row


def test_workflow_page_saves_roi_bindings_and_outputs(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    facade = _facade(tmp_path)
    page = WorkflowPage(facade)
    page._show_workflow(facade.list_workflows()[0])
    page._binding_table.setItem(0, 0, QTableWidgetItem("contact_result"))
    binding_combo = page._binding_table.cellWidget(0, 1)
    binding_combo.setEditText("roi_status")
    page._output_table.setItem(0, 0, QTableWidgetItem("selected_contact"))
    output_combo = page._output_table.cellWidget(0, 1)
    output_combo.setEditText("contact_result")

    workflow = page._build_form_workflow()
    saved = facade.update_workflow(workflow)

    assert saved.roi_bindings == {"contact_result": "roi_status"}
    assert [(out.key, out.source) for out in saved.outputs] == [("selected_contact", "contact_result")]


    _app()
    from smartaccess.desktop.viewmodels.base import EventRelay
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    facade = _facade(tmp_path)
    relay = EventRelay(facade)
    vm = MonitoringViewModel(facade, relay)
    logs: list[str] = []
    vm.log_line.connect(logs.append)

    workflow = facade.list_workflows()[0]
    facade.start_run(workflow=workflow)  # synchronous: same-thread signals fire directly

    assert logs  # runtime events were relayed to the view model
