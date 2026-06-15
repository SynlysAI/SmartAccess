from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.shared.config.settings import AppSettings  # noqa: E402
from smartaccess.shared.contracts.workflow import (  # noqa: E402
    WorkflowContract,
    WorkflowMetadata,
    WorkflowStep,
)
from smartaccess.shared.events.bus import RuntimeEvent  # noqa: E402
from smartaccess.shared.events.runtime import RuntimeEventName  # noqa: E402

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


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
            },
            {
                "id": "operator_note",
                "roi": {"x": 10, "y": 80, "width": 180, "height": 32},
                "normalized_roi": {
                    "x": 0.01,
                    "y": 0.08,
                    "width": 0.18,
                    "height": 0.03,
                },
                "action_bindings": [{"action": "type"}],
            },
        ],
    )
    facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_test",
                author="test",
                anchor_profile="d1",
                experiment_type="smoke_test",
                lifecycle_state="Draft",
                template_id="tpl_demo",
                template_version="1.0.0",
            ),
            steps=[
                WorkflowStep(
                    id="start",
                    action="click",
                    anchor_id="status_button",
                    expected_text="Running",
                    match_mode="contains",
                    timeout_seconds=1,
                )
            ],
        )
    )
    facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_missing",
                author="test",
                anchor_profile="missing_device",
                lifecycle_state="Draft",
            ),
            steps=[WorkflowStep(id="start", action="click", anchor_id="status_button")],
        )
    )
    return facade


def test_monitoring_vm_describes_selected_workflow_device(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    facade = _facade(tmp_path)
    vm = MonitoringViewModel(facade)

    summary = vm.workflow_summary("wf_test")

    assert summary.workflow_id == "wf_test"
    assert summary.anchor_profile == "d1"
    assert summary.device_found is True
    assert summary.title_contains == "ElectroChem Console"
    assert summary.anchor_count == 2
    assert summary.ocr_anchor_count == 1
    assert summary.actions == ["click", "type", "hotkey", "press_enter"]
    assert summary.template_label == "tpl_demo@1.0.0"


def test_monitoring_vm_reports_missing_bound_device(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    facade = _facade(tmp_path)
    vm = MonitoringViewModel(facade)

    summary = vm.workflow_summary("wf_missing")

    assert summary.workflow_id == "wf_missing"
    assert summary.anchor_profile == "missing_device"
    assert summary.device_found is False
    assert summary.status_text == "未找到绑定设备配置"


def test_monitoring_page_refreshes_workflow_device_info(tmp_path: Path) -> None:
    _app()
    from smartaccess.desktop.pages.monitoring_page import MonitoringPage

    facade = _facade(tmp_path)
    page = MonitoringPage(facade)

    page._workflow_combo.setCurrentIndex(page._workflow_combo.findData("wf_test"))
    _app().processEvents()

    info = page._workflow_info.toPlainText()
    assert "wf_test" in info
    assert "d1" in info
    assert "ElectroChem Console" in info
    assert "锚点: 2" in info
    assert "OCR观测: 1" in info
    html = page._workflow_info.toHtml()
    assert "工作流绑定设备" in html
    assert "绑定设备" in html
    assert page._workflow_info.lineWrapMode() == page._workflow_info.LineWrapMode.WidgetWidth
    assert page._workflow_info.maximumHeight() >= 140
    assert " / " not in page._workflow_info.toPlainText()
    summary = page._vm.workflow_summary("wf_test")
    source_html = page._workflow_info_html(summary)
    assert "<table" in source_html
    assert 'width="33%"' in source_html
    assert "\u57fa\u7840\u4fe1\u606f" in source_html
    assert "\u8bbe\u5907\u8bc4\u4f30" in source_html
    assert "\u80fd\u529b\u8bc4\u4f30" in source_html

    page._workflow_combo.setCurrentIndex(page._workflow_combo.findData("wf_missing"))
    _app().processEvents()

    assert "未找到绑定设备配置" in page._workflow_info.toPlainText()
    assert "未找到绑定设备配置" in page._workflow_info.toHtml()


def test_monitoring_page_observation_audit_uses_rich_text() -> None:
    _app()
    from smartaccess.desktop.pages.monitoring_page import MonitoringPage

    event = RuntimeEvent(
        name=RuntimeEventName.RUN_STEP_OBSERVED,
        session_id="run_1",
        timestamp=datetime(2026, 6, 15, 1, 2, 3, tzinfo=timezone.utc),
        payload={
            "step_id": "step_4",
            "match_mode": "contains",
            "expected_text": "肖旭",
            "actual_text": "当前识别: 肖旭",
            "matched": True,
            "attempts": 2,
            "elapsed_seconds": 1.2,
            "screenshot_path": "workspace/runs/run_1/screenshots/step_4.png",
        },
    )

    html = MonitoringPage._observation_html(event)

    assert "最新 OCR 观测" in html
    assert "contains 肖旭" in html
    assert "当前识别: 肖旭" in html
    assert "step_4.png" in html


def test_ocr_observation_log_includes_rule_actual_match_and_attempts() -> None:
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    entry = MonitoringViewModel._log_entry(
        RuntimeEvent(
            name=RuntimeEventName.RUN_STEP_OBSERVED,
            session_id="run_1",
            timestamp=datetime(2026, 6, 15, 1, 2, 3, tzinfo=timezone.utc),
            payload={
                "step_id": "start",
                "match_mode": "contains",
                "expected_text": "Running",
                "actual_text": "Status: Running",
                "matched": True,
                "attempts": 3,
            },
        )
    )

    assert "OCR规则: contains Running" in entry.message
    assert "OCR实际: Status: Running" in entry.message
    assert "匹配: True" in entry.message
    assert "尝试: 3" in entry.message


def test_ocr_failed_log_includes_rule_actual_match_and_attempts() -> None:
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    entry = MonitoringViewModel._log_entry(
        RuntimeEvent(
            name=RuntimeEventName.RUN_FAILED,
            session_id="run_1",
            timestamp=datetime(2026, 6, 15, 1, 2, 3, tzinfo=timezone.utc),
            payload={
                "step_id": "step_4",
                "detail": "OCR 结果未满足期望",
                "match_mode": "contains",
                "expected_text": "肖旭",
                "actual_text": "识别到了小旭",
                "matched": False,
                "attempts": 4,
            },
        )
    )

    assert entry.level == "ERROR"
    assert "OCR规则: contains 肖旭" in entry.message
    assert "OCR实际: 识别到了小旭" in entry.message
    assert "匹配: False" in entry.message
    assert "尝试: 4" in entry.message


def test_log_view_renders_error_and_ocr_fields_as_html() -> None:
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitorLogEntry
    from smartaccess.desktop.widgets.log_view import LogView

    _app()
    view = LogView()
    assert view.lineWrapMode() == view.LineWrapMode.WidgetWidth
    view.set_entries([
        MonitorLogEntry(
            timestamp="16:10:01",
            level="ERROR",
            message=(
                "run.failed / step_4 / OCR规则: contains 肖旭 / "
                "OCR实际: 识别到了小旭 / 匹配: False / 尝试: 4 / OCR 结果未满足期望"
            ),
            session_id="run_1",
            step_id="step_4",
        )
    ])

    plain = view.toPlainText()
    html = view.toHtml()
    assert "OCR规则" in html
    assert "contains 肖旭" in plain
    assert "OCR实际" in html
    assert "识别到了小旭" in plain
    assert "ERROR" in html
    assert "white-space:nowrap" not in html
    assert "margin-bottom:6px" not in html
    assert "margin-bottom:3px" not in html
    assert "margin-top:2px" not in html
    assert "margin:2px 0 6px 0" not in html


def test_non_ocr_observation_log_keeps_short_message() -> None:
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    entry = MonitoringViewModel._log_entry(
        RuntimeEvent(
            name=RuntimeEventName.RUN_STEP_OBSERVED,
            session_id="run_1",
            timestamp=datetime(2026, 6, 15, 1, 2, 3, tzinfo=timezone.utc),
            payload={
                "step_id": "wait",
                "match_mode": "none",
                "matched": None,
                "attempts": 1,
            },
        )
    )

    assert entry.message == "run.step.observed / wait"
    assert "OCR规则" not in entry.message


def test_non_ocr_failed_log_keeps_short_message() -> None:
    from smartaccess.desktop.viewmodels.monitoring_vm import MonitoringViewModel

    entry = MonitoringViewModel._log_entry(
        RuntimeEvent(
            name=RuntimeEventName.RUN_FAILED,
            session_id="run_1",
            timestamp=datetime(2026, 6, 15, 1, 2, 3, tzinfo=timezone.utc),
            payload={"step_id": "step_1", "detail": "未找到目标窗口: 微信"},
        )
    )

    assert entry.message == "run.failed / step_1 / 未找到目标窗口: 微信"
    assert "OCR规则" not in entry.message
