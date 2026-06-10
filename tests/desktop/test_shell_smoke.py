from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication, QTableWidgetItem  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.desktop.journey_projection import build_journey_projection  # noqa: E402
from smartaccess.desktop.widgets.workflow_journey import WorkflowJourneyGraph  # noqa: E402
from smartaccess.shared.config.settings import AppSettings  # noqa: E402
from smartaccess.shared.contracts.workflow import (  # noqa: E402
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowStep,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _empty_facade(tmp_path: Path):
    return build_runtime_facade(AppSettings(workspace_dir=tmp_path))


def _facade(tmp_path: Path):
    facade = _empty_facade(tmp_path)
    facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[
            {
                "id": "start_button",
                "type": "button",
                "vision_mode": "none",
                "action_bindings": [{"action": "click", "requires_confirmation": True}],
            },
            {
                "id": "roi_status",
                "type": "observation",
                "vision_mode": "ocr",
                "action_bindings": [{"action": "wait_until", "requires_confirmation": False}],
            },
        ],
        actions=["click", "wait_until"],
        safety_limits={
            "requires_manual_confirm_for": ["start_button"],
            "fields": [
                {
                    "field_id": "target_voltage",
                    "label": "目标电压",
                    "risk_level": "high",
                    "requires_confirmation": True,
                }
            ],
        },
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
    facade.generate_workflow(
        "打开方法编辑器，启动运行，并等待状态变化。",
        {"workflow_id": "wf_generated", "instrument_profile": "d1"},
    )
    return facade


def _projection(facade) -> object:
    dashboard = facade.dashboard()
    workflows = facade.list_workflows()
    checks = {wf.metadata.workflow_id: facade.standardize(wf) for wf in workflows}
    templates = facade.list_templates()
    return build_journey_projection(dashboard, workflows, checks, templates)


def test_main_window_builds_and_navigates(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.shell.main_window import MainWindow

    facade = _facade(tmp_path)
    window = MainWindow(facade)

    labels = [window._nav.item(i).text() for i in range(window._nav.count())]
    assert window._stack.count() == 6
    assert "流程引导" in labels[0]
    assert "设备接入与校准" in labels[1]
    assert "工作流设计" in labels[2]
    assert "模板库" in labels[3]
    assert "运行监控" in labels[4]
    assert "运行概览" in labels[5]
    assert all("流程总览" not in label for label in labels)
    for row in range(6):
        window._nav.setCurrentRow(row)
        assert window._stack.currentIndex() == row


def test_workflow_page_shows_context_snapshot_and_saves_outputs(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    facade = _facade(tmp_path)
    page = WorkflowPage(facade)
    generated = next(wf for wf in facade.list_workflows() if wf.metadata.workflow_id == "wf_generated")
    page._show_workflow(generated)

    assert page._prompt_label.text() == "Prompt / 目标描述"
    assert page._workflow_id_label.text() == "工作流 ID"
    assert page._device_label.text() == "目标设备"
    assert "ElectroChem Console" in page._reference_panel.toPlainText()
    assert "roi_status" in page._reference_panel.toPlainText()
    assert "start_button" in page._reasoning.toPlainText()
    assert "本次生成读取的上下文快照" in page._reasoning.toPlainText()

    page._step_conditions[0] = {
        "source": "roi_status",
        "mode": "ocr",
        "operator": "contains",
        "expected": "Running",
        "timeout_seconds": 12.0,
    }
    condition_button = page._make_condition_button(0)
    assert "roi_status" in condition_button.text()
    assert "contains" in condition_button.text()
    page._delete_step_row(0)
    assert 0 not in page._step_conditions

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


def test_journey_projection_empty_workspace(tmp_path: Path) -> None:
    facade = _empty_facade(tmp_path)
    projection = _projection(facade)
    statuses = [stage.status for stage in projection.stages]
    assert statuses == ["current", "future", "future", "future"]


def test_journey_projection_only_device(tmp_path: Path) -> None:
    facade = _empty_facade(tmp_path)
    facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[],
        actions=["click"],
        safety_limits={},
    )
    projection = _projection(facade)
    statuses = [stage.status for stage in projection.stages]
    assert statuses == ["completed", "current", "future", "future"]


def test_journey_projection_blocked_workflow(tmp_path: Path) -> None:
    facade = _empty_facade(tmp_path)
    facade.create_calibration(
        device_id="d1",
        title_contains="ElectroChem Console",
        anchors=[],
        actions=["click"],
        safety_limits={},
    )
    facade.register_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_blocked",
                author="test",
                instrument_profile="d1",
                experiment_type="smoke_test",
                lifecycle_state="Draft",
            ),
            roi_bindings={},
            steps=[],
            outputs=[],
        )
    )
    projection = _projection(facade)
    assert projection.stages[1].status == "blocked"


def test_journey_projection_published_but_not_run(tmp_path: Path) -> None:
    facade = _facade(tmp_path)
    workflow = next(wf for wf in facade.list_workflows() if wf.metadata.workflow_id == "wf_test")
    workflow.metadata.template_id = "tpl_demo"
    workflow.metadata.template_version = "1.0.0"
    workflow.metadata.lifecycle_state = "Published"
    facade.publish_template(workflow)
    projection = _projection(facade)
    assert projection.stages[3].status == "current"


def test_journey_graph_click_and_journey_page_navigation(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.journey_page import JourneyPage

    facade = _facade(tmp_path)
    page = JourneyPage(facade)
    projection = _projection(facade)
    graph = WorkflowJourneyGraph()
    graph.resize(960, 320)
    graph.set_projection(projection)
    graph.repaint()

    first_stage = projection.stages[0]
    center = graph._geometries[0].circle.center()
    assert graph.stage_at(center) == first_stage.stage_id

    emitted: list[str] = []
    graph.stage_clicked.connect(emitted.append)
    graph.stage_clicked.emit(first_stage.stage_id)
    assert emitted[-1] == "calibration"

    nav_rows: list[int] = []
    page.navigate_requested.connect(nav_rows.append)
    page._continue_to_next()
    assert nav_rows[-1] == page._projection.cta_target_page_index


def test_journey_graph_scales_to_avoid_clipping(tmp_path: Path) -> None:
    _app()

    facade = _facade(tmp_path)
    projection = _projection(facade)
    graph = WorkflowJourneyGraph()
    graph.resize(760, 320)
    graph.set_projection(projection)
    graph.repaint()

    assert len(graph._geometries) == len(projection.stages)
    assert graph._layout_scale < 1.0

    bounds = graph.rect()
    for geometry in graph._geometries:
        assert bounds.contains(geometry.circle.toRect())
        assert bounds.contains(geometry.card.toRect())


def test_monitoring_vm_receives_runtime_events(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.viewmodels.base import EventRelay
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    facade = _facade(tmp_path)
    relay = EventRelay(facade)
    vm = MonitoringViewModel(facade, relay)
    logs: list[str] = []
    readings: list[str] = []
    vm.log_line.connect(logs.append)
    vm.reading.connect(readings.append)

    workflow = facade.list_workflows()[0]
    facade.start_run(workflow=workflow)

    assert logs
    assert readings
    assert "roi_status" in readings[-1]
    assert "confidence" in readings[-1]
