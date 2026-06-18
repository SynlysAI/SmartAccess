from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QComboBox  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.desktop.pages.workflow_page import WorkflowPage  # noqa: E402
from smartaccess.desktop.widgets.workflow_step_table import (  # noqa: E402
    StepRow,
    WorkflowStepTable,
)
from smartaccess.shared.config.settings import AppSettings  # noqa: E402

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def _combo_values(combo: QComboBox) -> list[str]:
    return [str(combo.itemData(index) or "") for index in range(combo.count())]


def _anchor(anchor_id: str) -> dict:
    return {
        "id": anchor_id,
        "action_region": {
            "pixel": {"x": 1, "y": 2, "width": 30, "height": 20},
            "normalized": {"x": 0.01, "y": 0.02, "width": 0.1, "height": 0.1},
        },
        "supported_actions": ["click"],
    }


def test_anchor_options_follow_selected_view() -> None:
    _app()
    table = WorkflowStepTable()
    table.set_steps(
        [StepRow(step_id="s1", action="click", view_id="main", anchor_id="main_box")],
        ["main_box", "dialog_button"],
        ["main", "view_1"],
        anchors_by_view={
            "main": ["main_box"],
            "view_1": ["dialog_button"],
        },
    )

    view = table.cellWidget(0, 2)
    anchor = table.cellWidget(0, 3)
    assert isinstance(view, QComboBox)
    assert isinstance(anchor, QComboBox)
    assert _combo_values(anchor) == ["", "main_box"]

    view.setCurrentIndex(view.findData("view_1"))

    anchor = table.cellWidget(0, 3)
    assert isinstance(anchor, QComboBox)
    assert _combo_values(anchor) == ["", "dialog_button"]
    assert anchor.currentData() == ""


def test_wait_step_preserves_anchor_and_condition_when_read_from_table() -> None:
    _app()
    table = WorkflowStepTable()
    table.set_steps(
        [
            StepRow(
                step_id="wait_for_dialog",
                action="wait",
                view_id="dialog_reset_done",
                anchor_id="reset_done_text",
                match_mode="contains",
                expected_text="复位结束",
                timeout_seconds=30,
            )
        ],
        ["main_box", "reset_done_text"],
        ["main", "dialog_reset_done"],
        anchors_by_view={
            "main": ["main_box"],
            "dialog_reset_done": ["reset_done_text"],
        },
    )

    row = table.rows()[0]

    assert row.action == "wait"
    assert row.view_id == "dialog_reset_done"
    assert row.anchor_id == "reset_done_text"
    assert row.match_mode == "contains"
    assert row.expected_text == "复位结束"
    assert row.timeout_seconds == 30


def test_insert_wait_ocr_and_manual_confirmation_steps() -> None:
    _app()
    table = WorkflowStepTable()
    table.set_steps(
        [],
        ["main_box", "dialog_text"],
        ["main", "dialog_done"],
        anchors_by_view={
            "main": ["main_box"],
            "dialog_done": ["dialog_text"],
        },
    )

    table.insert_wait_ocr(0)
    table.insert_manual_confirm(1)
    rows = table.rows()

    assert rows[0].action == "wait"
    assert rows[0].anchor_id == "main_box"
    assert rows[0].match_mode == "not_empty"
    assert rows[0].timeout_seconds == 30
    assert rows[1].action == "wait"
    assert rows[1].anchor_id is None
    assert rows[1].match_mode == "none"
    assert rows[1].requires_confirmation is True


def test_workflow_page_passes_view_anchor_mapping(tmp_path) -> None:
    _app()
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id="d1",
        title_contains="Main",
        capture_width=800,
        capture_height=600,
        anchors=[],
        views=[
            {
                "view_id": "main",
                "window_signature": {"title_contains": "Main"},
                "anchors": [_anchor("main_box")],
            },
            {
                "view_id": "view_1",
                "window_signature": {"title_contains": "Dialog"},
                "anchors": [_anchor("dialog_button")],
            },
        ],
    )
    page = WorkflowPage(facade)
    page._steps.insert_action(0)

    view = page._steps.cellWidget(0, 2)
    anchor = page._steps.cellWidget(0, 3)
    assert isinstance(view, QComboBox)
    assert isinstance(anchor, QComboBox)
    assert _combo_values(anchor) == ["", "main_box"]

    view.setCurrentIndex(view.findData("view_1"))

    anchor = page._steps.cellWidget(0, 3)
    assert isinstance(anchor, QComboBox)
    assert _combo_values(anchor) == ["", "dialog_button"]
