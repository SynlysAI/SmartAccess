from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QDialogButtonBox,
    QLineEdit,
    QPushButton,
)

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.desktop.pages.workflow_page import WorkflowPage  # noqa: E402
from smartaccess.desktop.widgets.workflow_step_table import (  # noqa: E402
    IncrementRuleDialog,
    InputValueEditor,
    StepRow,
    WorkflowStepTable,
)
from smartaccess.shared.config.settings import AppSettings  # noqa: E402

_APP: QApplication | None = None
DEVICE_ID = "氟基-2236实验室-元能极片电阻仪-01"


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


def test_type_step_input_mode_round_trips_and_wait_disables_mode() -> None:
    _app()
    table = WorkflowStepTable()
    table.set_steps(
        [
            StepRow(
                step_id="sample_id",
                action="type",
                anchor_id="input",
                input_mode="incrementing",
            ),
            StepRow(step_id="wait_1", action="wait", wait_seconds=1.0),
        ],
        ["input"],
    )

    type_row, wait_row = table.rows()
    mode = table.cellWidget(1, 5)

    assert type_row.input_mode == "incrementing"
    assert type_row.increment_rule == {
        "pattern": "{device_id}-{author}-{date}-{counter:03d}",
        "start": 1,
        "width": 3,
        "sequence_key": "default",
        "date_format": "%Y%m%d",
        "min_value": None,
        "max_value": None,
        "cycle": False,
    }
    assert wait_row.input_mode == "free"
    assert mode is not None
    assert mode.isEnabled() is False


def test_increment_rule_round_trips_without_resetting_to_default() -> None:
    _app()
    custom_rule = {
        "pattern": "{workflow_id}-{counter:02d}",
        "start": 0,
        "width": 2,
        "sequence_key": "sample_name",
        "date_format": "%Y-%m-%d",
        "min_value": 0,
        "max_value": 100,
        "cycle": True,
    }
    table = WorkflowStepTable()
    table.set_steps(
        [
            StepRow(
                step_id="sample_id",
                action="type",
                anchor_id="input",
                input_mode="incrementing",
                increment_rule=custom_rule,
            )
        ],
        ["input"],
    )

    row = table.rows()[0]

    assert row.value is None
    assert row.input_mode == "incrementing"
    assert row.increment_rule == custom_rule


def test_value_cell_switches_between_free_and_incrementing_modes() -> None:
    _app()
    table = WorkflowStepTable()
    table.set_steps(
        [StepRow(step_id="sample_id", action="type", anchor_id="input", value="abc")],
        ["input"],
    )
    mode = table.cellWidget(0, 5)
    value = table.cellWidget(0, 4)
    assert isinstance(mode, QComboBox)
    assert isinstance(value, InputValueEditor)

    assert table.rows()[0].value == "abc"
    mode.setCurrentIndex(mode.findData("incrementing"))

    row = table.rows()[0]
    assert row.value is None
    assert row.input_mode == "incrementing"
    assert row.increment_rule == {
        "pattern": "{device_id}-{author}-{date}-{counter:03d}",
        "start": 1,
        "width": 3,
        "sequence_key": "default",
        "date_format": "%Y%m%d",
        "min_value": None,
        "max_value": None,
        "cycle": False,
    }


def test_increment_rule_dialog_updates_width_and_validates_pattern() -> None:
    app = _app()
    dialog = IncrementRuleDialog(
        {
            "pattern": "{workflow_id}-{counter:03d}",
            "start": 1,
            "width": 3,
            "sequence_key": "sample_name",
            "date_format": "%Y-%m-%d",
            "max_value": 10,
            "cycle": True,
        },
        {"workflow_id": "wf_demo"},
    )
    pattern = dialog._pattern

    dialog._width.setValue(4)
    app.processEvents()

    assert pattern.text() == "{workflow_id}-{counter:04d}"
    assert dialog.rule()["width"] == 4
    assert dialog.rule()["sequence_key"] == "sample_name"
    assert dialog.rule()["date_format"] == "%Y-%m-%d"
    assert dialog.rule()["max_value"] == 10
    assert dialog.rule()["cycle"] is True

    pattern.setText("{workflow_id}")
    app.processEvents()
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok is not None
    assert ok.isEnabled() is False


def test_increment_value_editor_config_button_is_visible_for_incrementing() -> None:
    _app()
    editor = InputValueEditor(input_mode="incrementing")
    buttons = editor.findChildren(QPushButton)

    assert any(button.text() for button in buttons)
    assert editor.increment_rule() == {
        "pattern": "{device_id}-{author}-{date}-{counter:03d}",
        "start": 1,
        "width": 3,
        "sequence_key": "default",
        "date_format": "%Y%m%d",
        "min_value": None,
        "max_value": None,
        "cycle": False,
    }


def test_workflow_page_passes_view_anchor_mapping(tmp_path) -> None:
    _app()
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))
    facade.create_calibration(
        device_id=DEVICE_ID,
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
