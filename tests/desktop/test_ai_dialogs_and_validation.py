from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from smartaccess.bootstrap import build_runtime_facade  # noqa: E402
from smartaccess.desktop.widgets.anchor_table import AnchorRow  # noqa: E402
from smartaccess.runtime.application.ports import WindowInfo  # noqa: E402
from smartaccess.shared.config.settings import AppSettings  # noqa: E402
from smartaccess.shared.contracts.workflow import WorkflowContract, WorkflowMetadata, WorkflowStep  # noqa: E402
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
                "normalized_roi": {"x": 0.01, "y": 0.01, "width": 0.08, "height": 0.03},
                "action_bindings": [{"action": "click", "requires_confirmation": True}],
            }
        ],
    )
    facade.save_workflow(
        WorkflowContract(
            metadata=WorkflowMetadata(
                workflow_id="wf_test",
                author="test",
                anchor_profile="d1",
                lifecycle_state="Draft",
            ),
            steps=[WorkflowStep(id="start", action="click", anchor_id="status_button")],
        )
    )
    return facade


def _anchor_payload(anchor_id: str) -> dict:
    return {
        "id": anchor_id,
        "action_region": {
            "pixel": {"x": 1, "y": 2, "width": 30, "height": 20},
            "normalized": {"x": 0.01, "y": 0.02, "width": 0.1, "height": 0.1},
        },
        "supported_actions": ["click"],
        "action_bindings": [{"action": "click", "requires_confirmation": False}],
    }


def test_ai_prompt_dialog_wraps_text_and_exposes_busy_state() -> None:
    _app()
    from smartaccess.desktop.widgets.ai_dialogs import AiPromptDialog

    dialog = AiPromptDialog(
        title="AI生成工作流",
        label="输入实验步骤",
        ai_label="stub / test",
        initial_text="",
    )
    editor = dialog.findChild(QPlainTextEdit)

    assert editor is not None
    assert editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
    assert editor.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    dialog.set_busy(True, "AI生成中")
    assert not dialog._busy_label.isHidden()
    assert "AI生成中" in dialog._busy_label.text()
    assert not dialog._ok.isEnabled()

    dialog.set_busy(False)
    assert dialog._busy_label.isHidden()
    assert dialog._ok.isEnabled()


def test_calibration_ai_requires_device_id_and_title(tmp_path: Path, monkeypatch) -> None:
    _app()
    from smartaccess.desktop.pages.calibration_page import CalibrationPage

    page = CalibrationPage(_facade(tmp_path))
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "smartaccess.desktop.pages.calibration_page.QMessageBox.warning",
        lambda _parent, title, text: messages.append((title, text)),
    )

    page._device_id.clear()
    page._title_contains.clear()

    assert page._require_device_fields() is None
    assert messages
    assert "设备 ID" in messages[-1][1]
    assert "窗口标题" in messages[-1][1]


def test_calibration_scan_refreshes_all_windows_after_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    from smartaccess.desktop.pages.calibration_page import CalibrationPage

    page = CalibrationPage(_facade(tmp_path))
    monkeypatch.setattr(
        page._vm,
        "discover_windows",
        lambda: [
            WindowInfo(title="Calculator", width=612, height=750, matched=True, hwnd=1),
            WindowInfo(title="WeChat", width=1290, height=1175, matched=True, hwnd=2),
        ],
    )

    page._discover()
    page._windows.setCurrentRow(0)
    assert page._title_contains.text() == "Calculator"
    assert page._selected_hwnd == 1
    assert page._capture_btn.isEnabled()

    page._discover()

    labels = [page._windows.item(index).text() for index in range(page._windows.count())]
    assert len(labels) == 2
    assert any("Calculator" in label for label in labels)
    assert any("WeChat" in label for label in labels)
    assert page._selected_hwnd is None
    assert not page._capture_btn.isEnabled()


def test_calibration_save_preserves_main_capture_when_current_view_is_dialog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    from smartaccess.desktop.pages.calibration_page import CalibrationPage

    facade = _facade(tmp_path)
    page = CalibrationPage(facade)
    monkeypatch.setattr(
        "smartaccess.desktop.pages.calibration_page.QMessageBox.information",
        lambda *_args: None,
    )

    page._device_id.setText("multi_device")
    page._title_contains.setText("Dialog")
    page._view_states = {
        "main": {
            "title": "Main",
            "capture": b"main-capture",
            "anchors": [_anchor_payload("start")],
            "capture_width": 800,
            "capture_height": 600,
        },
        "dialog_confirm": {
            "title": "Dialog",
            "capture": b"old-dialog-capture",
            "anchors": [],
            "capture_width": 360,
            "capture_height": 220,
        },
    }
    page._current_view_id = "dialog_confirm"
    page._latest_capture = b"dialog-capture"
    page._canvas.clear_all()
    page._table.setRowCount(0)
    page._canvas.add_roi("ok", 1, 2, 30, 20)
    page._table.add_anchor(AnchorRow(anchor_id="ok", action_roi="ok"))

    page._save()

    assert facade.load_instrument_capture("multi_device") == b"main-capture"
    assert (
        facade.load_instrument_capture("multi_device", view_id="dialog_confirm")
        == b"dialog-capture"
    )
    profile = facade.get_instrument("multi_device")
    assert profile is not None
    assert profile.window_signature.capture_width == 800
    assert profile.window_signature.capture_height == 600


def test_calibration_ai_overwrites_current_view_without_resetting_to_main(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    from smartaccess.desktop.pages.calibration_page import CalibrationPage
    from smartaccess.shared.contracts.anchors import AnchorsContract

    page = CalibrationPage(_facade(tmp_path))
    monkeypatch.setattr(
        "smartaccess.desktop.pages.calibration_page.QMessageBox.information",
        lambda *_args: None,
    )

    main_capture = b"main-capture"
    view_capture = b"view-new-capture"
    main_anchor = _anchor_payload("main_saved")
    old_view_anchor = _anchor_payload("old_view_anchor")
    ai_anchor = _anchor_payload("ai_generated")
    page._view_states = {
        "main": {
            "title": "Main",
            "capture": main_capture,
            "anchors": [main_anchor],
            "capture_width": 800,
            "capture_height": 600,
        },
        "view_new": {
            "title": "Dialog",
            "capture": view_capture,
            "anchors": [old_view_anchor],
            "capture_width": None,
            "capture_height": None,
        },
    }
    page._current_view_id = "view_new"
    page._latest_capture = view_capture
    page._load_view_state("view_new")
    page._ai_target_view_id = "view_new"

    result = AnchorsContract.model_validate(
        {
            "profile_id": "multi_device",
            "window_signature": {
                "title_contains": "Main",
                "screenshot_size": {"width": 800, "height": 600},
            },
            "views": [
                {
                    "view_id": "main",
                    "window_signature": {
                        "title_contains": "Main",
                        "screenshot_size": {"width": 800, "height": 600},
                    },
                    "screenshot_size": {"width": 800, "height": 600},
                    "anchors": [ai_anchor],
                }
            ],
        }
    )

    page._on_ai_assist_done(result)

    assert page._current_view_id == "view_new"
    assert page._view_states["main"]["anchors"] == [main_anchor]
    assert [
        anchor["id"] for anchor in page._view_states["view_new"]["anchors"]
    ] == ["ai_generated"]
    assert page._view_states["view_new"]["capture_width"] == 800
    assert page._view_states["view_new"]["capture_height"] == 600
    assert page._latest_capture == view_capture
    assert [row.anchor_id for row in page._table.row_models()] == ["ai_generated"]


def test_calibration_preview_current_view_ocr_reads_observe_anchor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    from smartaccess.desktop.pages.calibration_page import CalibrationPage

    facade = _facade(tmp_path)
    page = CalibrationPage(facade)
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "smartaccess.desktop.pages.calibration_page.QMessageBox.information",
        lambda _parent, title, text: shown.append((title, text)),
    )

    capture = b"current-dialog-capture"
    anchor = _anchor_payload("dialog_text")
    anchor["observe_region"] = anchor["action_region"]
    page._view_states = {
        "main": {
            "title": "Main",
            "capture": b"main-capture",
            "anchors": [],
            "capture_width": 800,
            "capture_height": 600,
        },
        "dialog_done": {
            "title": "Dialog",
            "capture": capture,
            "anchors": [anchor],
            "capture_width": 800,
            "capture_height": 600,
        },
    }
    page._current_view_id = "dialog_done"
    page._load_view_state("dialog_done")
    monkeypatch.setattr(
        page._vm,
        "preview_anchor_ocr",
        lambda *, capture_data, anchor_payload: (
            "实验结束" if capture_data == capture and anchor_payload["id"] == "dialog_text" else ""
        ),
    )

    page._preview_current_view_ocr()

    assert shown
    assert shown[-1][0] == "OCR预览"
    assert "实验结束" in shown[-1][1]


def test_workflow_ai_requires_workflow_id_and_device(tmp_path: Path, monkeypatch) -> None:
    _app()
    from smartaccess.desktop.pages.workflow_page import WorkflowPage

    page = WorkflowPage(_facade(tmp_path))
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "smartaccess.desktop.pages.workflow_page.QMessageBox.warning",
        lambda _parent, title, text: messages.append((title, text)),
    )

    page._workflow_id.clear()
    page._anchor_profile.setCurrentIndex(-1)

    assert page._require_workflow_fields() is None
    assert messages
    assert "工作流 ID" in messages[-1][1]
    assert "设备" in messages[-1][1]


def test_monitoring_page_handles_blocked_confirmation_and_window_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _app()
    from smartaccess.desktop.pages.monitoring_page import MonitoringPage
    from smartaccess.shared.events.bus import RuntimeEvent

    page = MonitoringPage(_facade(tmp_path))
    questions: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        "smartaccess.desktop.pages.monitoring_page.QMessageBox.question",
        lambda _parent, title, text, *_args: (
            questions.append(f"{title}:{text}") or page._confirm_yes_button()
        ),
    )
    monkeypatch.setattr(
        "smartaccess.desktop.pages.monitoring_page.QMessageBox.warning",
        lambda _parent, title, text: warnings.append(f"{title}:{text}"),
    )

    page._on_event(
        RuntimeEvent(
            name=RuntimeEventName.RUN_BLOCKED,
            session_id="run_1",
            payload={"step_id": "start", "reason": "步骤 start 需要人工确认"},
        )
    )
    assert questions

    page._on_event(
        RuntimeEvent(
            name=RuntimeEventName.RUN_BLOCKED,
            session_id="run_1",
            payload={
                "incident_type": "WindowMissing",
                "anchor_profile": "d1",
                "title_contains": "ElectroChem Console",
                "detail": "未找到目标窗口",
            },
        )
    )
    assert warnings
    assert "d1" in warnings[-1]
    assert "ElectroChem Console" in warnings[-1]
