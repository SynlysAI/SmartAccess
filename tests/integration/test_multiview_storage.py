from __future__ import annotations

from pathlib import Path

from smartaccess.bootstrap import build_runtime_facade
from smartaccess.shared.config.settings import AppSettings

DEVICE_ID = "氟基-2236实验室-元能极片电阻仪-01"


def _anchor(anchor_id: str) -> dict:
    return {
        "id": anchor_id,
        "action_region": {
            "pixel": {"x": 1, "y": 2, "width": 30, "height": 20},
            "normalized": {"x": 0.01, "y": 0.02, "width": 0.1, "height": 0.1},
        },
        "supported_actions": ["click"],
    }


def test_create_calibration_persists_multiview_contract_and_view_captures(tmp_path: Path) -> None:
    facade = build_runtime_facade(AppSettings(workspace_dir=tmp_path))

    profile = facade.create_calibration(
        device_id=DEVICE_ID,
        title_contains="Main",
        capture_width=800,
        capture_height=600,
        anchors=[_anchor("start")],
        views=[
            {
                "view_id": "main",
                "window_signature": {
                    "title_contains": "Main",
                    "screenshot_size": {"width": 800, "height": 600},
                },
                "anchors": [_anchor("start")],
            },
            {
                "view_id": "dialog_confirm",
                "window_signature": {
                    "title_contains": "Confirm",
                    "screenshot_size": {"width": 360, "height": 220},
                },
                "anchors": [_anchor("ok")],
            },
        ],
    )
    facade.save_instrument_capture(profile.profile_id, b"main-capture")
    facade.save_instrument_capture(
        profile.profile_id,
        b"dialog-capture",
        view_id="dialog_confirm",
    )
    reloaded = facade.get_instrument(DEVICE_ID)

    assert reloaded is not None
    assert sorted(reloaded.view_map()) == ["dialog_confirm", "main"]
    assert reloaded.anchor_for_view("dialog_confirm", "ok") is not None
    assert facade.load_instrument_capture(DEVICE_ID) == b"main-capture"
    assert (
        facade.load_instrument_capture(DEVICE_ID, view_id="dialog_confirm")
        == b"dialog-capture"
    )
    assert (tmp_path / "anchors" / DEVICE_ID / "views" / "dialog_confirm" / "capture.png").exists()
