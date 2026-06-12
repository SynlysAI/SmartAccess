from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.desktop.journey_projection import build_journey_projection  # noqa: E402
from smartaccess.desktop.widgets.workflow_journey import WorkflowJourneyGraph  # noqa: E402
from smartaccess.runtime.application.workspace_settings import (  # noqa: E402
    AI_PROFILE_DEVICE_ONBOARDING,
    AI_PROFILE_WORKFLOW,
)
from smartaccess.shared.config.settings import AIProfileConfig, AppSettings  # noqa: E402
from smartaccess.shared.contracts import load_yaml_contract  # noqa: E402
from smartaccess.shared.contracts.workflow import (  # noqa: E402
    WorkflowContract,
    WorkflowMetadata,
    WorkflowOutput,
    WorkflowStep,
)

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def _empty_facade(tmp_path: Path):
    return build_runtime_facade(AppSettings(workspace_dir=tmp_path))


def _ai_profile_facade(tmp_path: Path):
    return build_runtime_facade(
        AppSettings(
            workspace_dir=tmp_path,
            ai_active_profile="codex",
            ai_profiles={
                "codex": AIProfileConfig(
                    profile_id="codex",
                    label="Codex",
                    provider="codex",
                    base_url="https://fufei.mossx.ai/v1",
                    model="GPT-5.4",
                    api_key="codex-key",
                ),
                "deepseek": AIProfileConfig(
                    profile_id="deepseek",
                    label="DeepSeek",
                    provider="deepseek",
                    base_url="https://api.deepseek.com",
                    model="deepseek-chat",
                    api_key="deepseek-key",
                ),
            },
        )
    )


def _facade(tmp_path: Path):
    facade = _empty_facade(tmp_path)
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
                "action_bindings": [{"action": "click", "requires_confirmation": True}],
                "vision_mode": "ocr",
            },
        ],
        actions=["click"],
        safety_limits={
            "requires_manual_confirm_for": ["status_button"],
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
                anchor_profile="d1",
                experiment_type="smoke_test",
                lifecycle_state="Draft",
            ),
            roi_bindings={"status_banner": "status_button"},
            steps=[
                WorkflowStep(
                    id="start_and_wait",
                    action="click",
                    anchor_id="status_button",
                    expected_text="Running",
                    match_mode="contains",
                    timeout_seconds=1.0,
                )
            ],
            outputs=[WorkflowOutput(key="run_status", source="status_button")],
        )
    )
    facade.generate_workflow(
        "打开方法编辑器，启动运行，并等待状态变化。",
        {"workflow_id": "wf_generated", "anchor_profile": "d1"},
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


def test_workflow_page_shows_ai_evidence_and_saves_without_outputs(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    facade = _facade(tmp_path)
    page = WorkflowPage(facade)
    assert page._prompt.toPlainText() == ""
    generated = next(wf for wf in facade.list_workflows() if wf.metadata.workflow_id == "wf_generated")
    page._show_workflow(generated)

    assert not page._draft_dock.isVisible()
    assert not page._review_dock.isVisible()
    assert page._prompt_label.text()
    assert page._workflow_id_label.text()
    assert page._anchor_profile_label.text() == "anchor_profile"
    assert page._editor_tabs.count() == 1
    assert page._editor_tabs.tabText(0) == "步骤编排"
    assert "ElectroChem Console" in page._reasoning.toPlainText()
    assert "status_button" in page._reasoning.toPlainText()
    assert "生成依据与编排过程" not in page._reasoning.toPlainText()
    assert "步骤编排" in page._reasoning.toPlainText()
    assert "知识命中" in page._reasoning.toPlainText()
    assert not hasattr(page, "_binding_table")
    assert not hasattr(page, "_output_table")

    page._set_row_condition(0, {
        "expected_text": "Running",
        "match_mode": "contains",
        "timeout_seconds": 12.0,
    })
    condition_button = page._make_condition_button(0)
    assert "OCR" in condition_button.text()
    assert "contains" in condition_button.text()
    page._delete_step_row(0)
    assert page._row_condition(0) is None

    workflow = page._build_form_workflow()
    saved = facade.update_workflow(workflow)

    assert saved.roi_bindings == {}
    assert saved.outputs == []
    serialized = saved.model_dump(mode="json", exclude_none=True)
    assert serialized["metadata"]["anchor_profile"] == "d1"
    assert "instrument_profile" not in serialized["metadata"]
    assert all("anchor_id" in step and "target" not in step for step in serialized["steps"])


def test_workflow_page_condition_round_trip_and_row_reorder(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    facade = _facade(tmp_path)
    workflow = next(wf for wf in facade.list_workflows() if wf.metadata.workflow_id == "wf_test")
    page = WorkflowPage(facade)
    page._show_workflow(workflow)

    button = page._steps_table.cellWidget(0, 4)
    assert button is not None
    assert "OCR" in button.text()
    assert "contains" in button.text()
    assert "Running" in button.text()

    page._insert_step_at("step_extra", "click", "status_button", "", 0)
    assert page._row_condition(0) is None
    assert page._row_condition(1)["expected_text"] == "Running"

    page._move_step_up(1)
    assert page._row_condition(0)["expected_text"] == "Running"
    assert page._row_condition(1) is None

    saved = facade.update_workflow(page._build_form_workflow())
    reloaded = load_yaml_contract(
        tmp_path / "workflows" / saved.metadata.workflow_id / "draft.yaml",
        WorkflowContract,
    )
    assert reloaded.steps[0].expected_text == "Running"
    assert reloaded.steps[0].match_mode == "contains"
    assert reloaded.steps[0].timeout_seconds == 1.0


def test_workflow_page_step_table_adapts_to_content_and_row_count(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    facade = _facade(tmp_path)
    workflow = WorkflowContract(
        metadata=WorkflowMetadata(
            workflow_id="wf_long_step_table",
            author="test",
            anchor_profile="d1",
            experiment_type="smoke_test",
            lifecycle_state="Draft",
        ),
        roi_bindings={},
        steps=[
            WorkflowStep(
                id="step_with_long_fields",
                action="type",
                anchor_id="anchor_id_for_a_wide_numeric_input_field",
                value="1234567890.1234567890",
                expected_text="measurement complete with stable baseline",
                match_mode="contains",
                timeout_seconds=12.0,
            )
        ],
        outputs=[],
    )
    page = WorkflowPage(facade)
    page.resize(980, 640)
    page._show_workflow(workflow)
    page.show()
    _app().processEvents()

    assert page._steps_table.maximumHeight() < 220
    assert page._steps_table.columnWidth(5) == 92
    assert page._steps_table.columnWidth(6) == 52
    assert page._steps_table.item(0, 2).toolTip() == "anchor_id_for_a_wide_numeric_input_field"
    assert sum(page._steps_table.columnWidth(column) for column in range(7)) <= (
        page._steps_table.viewport().width() + 4
    )


def test_workflow_page_uses_central_ai_profile_configuration(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    facade = _ai_profile_facade(tmp_path)
    facade.set_ai_profile_preference(AI_PROFILE_WORKFLOW, "deepseek")
    page = WorkflowPage(facade)

    assert not hasattr(page, "_ai_profile")
    assert page._workflow_ai_profile_id() == "deepseek"


def test_calibration_page_exposes_simplified_anchor_table(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.calibration_page import CalibrationPage

    facade = _ai_profile_facade(tmp_path)
    facade.set_ai_profile_preference(AI_PROFILE_DEVICE_ONBOARDING, "deepseek")
    page = CalibrationPage(facade)
    page._insert_anchor_row(name="status_button", roi_name="status_button", action="click")

    headers = [
        page._anchor_table.horizontalHeaderItem(i).text()
        for i in range(page._anchor_table.columnCount())
    ]
    assert "类型" not in headers
    assert headers[:6] == ["锚点ID", "动作区域", "主要动作", "OCR观测", "观测区域", "需确认"]

    action_combo = page._anchor_table.cellWidget(0, 2)
    actions = [action_combo.itemData(i) for i in range(action_combo.count())]
    assert actions == ["click", "type", "hotkey", "press_enter"]
    assert not hasattr(page, "_ai_profile")
    assert page._device_onboarding_ai_profile_id() == "codex"


def test_calibration_page_explains_codex_503_error() -> None:
    from smartaccess.desktop.pages.calibration_page import CalibrationPage

    message = CalibrationPage._friendly_ai_error(
        RuntimeError(
            "Codex anchor generation failed: HTTP 503: "
            "Service temporarily unavailable | api_error"
        )
    )

    assert "Codex 服务临时不可用" in message
    assert "HTTP 503" in message


def test_right_context_panel_persists_ai_profile_preferences(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.shell.main_window import MainWindow
    from PyQt6.QtWidgets import QLabel

    facade = _ai_profile_facade(tmp_path)
    window = MainWindow(facade)

    assert window._right._workflow_ai_profile.currentData() == "codex"
    assert window._right._device_ai_profile.currentData() == "codex"
    assert not window._right._device_ai_profile.isEnabled()
    assert window._right._device_ai_profile.findData("deepseek") == -1
    labels = [label.text() for label in window._right.assistant.findChildren(QLabel)]
    assert "配置工作流模型" in labels
    assert "设备接入模型选择" in labels
    assert labels.index("设备接入模型选择") < labels.index("配置工作流模型")
    assistant_text = "\n".join(labels)
    assert "接入模型:" not in assistant_text
    assert "状态:" not in assistant_text
    assert "提供方:" not in assistant_text
    assert "Configured" not in assistant_text
    assert "base_url" not in assistant_text

    window._right._workflow_ai_profile.setCurrentIndex(
        window._right._workflow_ai_profile.findData("deepseek")
    )

    assert facade.ai_profile_for_purpose(AI_PROFILE_WORKFLOW) == "deepseek"
    assert facade.ai_profile_for_purpose(AI_PROFILE_DEVICE_ONBOARDING) == "codex"
    assert (tmp_path / "config" / "app_settings.json").exists()


def test_monitoring_audit_card_shows_strategy_and_measurement() -> None:
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    html = MonitoringViewModel._format_audit_card(
        {
            "step_id": "step_1",
            "status": "observed",
            "action": "click",
            "anchor_id": "搜索结果",
            "match_mode": "contains",
            "expected_text": "文件传输助手",
            "actual_text": "文件传输助手",
            "matched": True,
            "attempts": 1,
            "elapsed_seconds": 0.5,
            "wait_strategy": {"type": "ocr_poll"},
            "screenshot_path": "workspace/runs/demo/screenshots/step_1.png",
            "trace_path": "workspace/runs/demo/run_trace.jsonl",
            "workflow_path": "workspace/workflows/demo/draft.yaml",
            "anchors_path": "workspace/anchors/weixin_01/anchors.yaml",
        }
    )

    assert "ocr_poll" in html
    assert "文件传输助手" in html
    assert "通过" in html
    assert "step_1.png" in html
    assert "href=" in html
    assert "run_trace.jsonl" in html
    assert "anchors.yaml" in html


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
                anchor_profile="d1",
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
    assert "status_button" in readings[-1]
    assert "confidence" in readings[-1]
