from __future__ import annotations

from dataclasses import dataclass

from smartaccess.runtime.adapters.win32_automation import Win32AutomationProvider
from smartaccess.shared.contracts.anchors import AnchorView, AnchorsContract


@dataclass(slots=True)
class _FakeWindow:
    """测试用窗口信息。"""

    hwnd: int
    title: str = "Clash for Windows"


class _FakeScanner:
    """记录窗口扫描参数的测试替身。"""

    def __init__(self) -> None:
        """初始化扫描记录。"""

        self.calls: list[tuple[str, str | None, bool]] = []

    def scan(self, *, include_disabled: bool = False, **_kwargs) -> list[_FakeWindow]:
        """模拟扫描全部窗口。"""

        self.calls.append(("scan", None, include_disabled))
        return [_FakeWindow(hwnd=1001)]

    def scan_equals(
        self,
        title: str,
        *,
        include_disabled: bool = False,
    ) -> list[_FakeWindow]:
        """模拟精确标题扫描。"""

        self.calls.append(("equals", title, include_disabled))
        return [_FakeWindow(hwnd=1002)]

    def scan_contains(
        self,
        substring: str,
        *,
        include_disabled: bool = False,
    ) -> list[_FakeWindow]:
        """模拟包含标题扫描。"""

        self.calls.append(("contains", substring, include_disabled))
        return [_FakeWindow(hwnd=1003)]


class _FakeUser32:
    """记录鼠标输入的测试替身。"""

    def __init__(self) -> None:
        """初始化输入记录。"""

        self.positions: list[tuple[int, int]] = []
        self.mouse_events: list[int] = []

    def SetCursorPos(self, x: int, y: int) -> bool:  # noqa: N802
        """记录光标位置。"""

        self.positions.append((x, y))
        return True

    def mouse_event(self, event: int, *_args) -> None:
        """记录鼠标事件。"""

        self.mouse_events.append(event)


def test_win32_window_present_includes_disabled_modal_owner() -> None:
    provider = object.__new__(Win32AutomationProvider)
    provider._scanner = _FakeScanner()
    provider._view = None
    provider._profile = None
    provider._hwnd = None

    assert provider.window_present("Clash for Windows") is True

    assert provider._scanner.calls == [
        ("contains", "Clash for Windows", True),
    ]
    assert provider._hwnd == 1003


def test_win32_configure_view_keeps_main_window_handle() -> None:
    provider = object.__new__(Win32AutomationProvider)
    provider._scanner = _FakeScanner()
    provider._view = None
    provider._profile = None
    provider._hwnd = None
    profile = AnchorsContract.model_validate(
        {
            "profile_id": "app",
            "window_signature": {"title_contains": "Main Window"},
            "views": [
                {
                    "view_id": "main",
                    "window_signature": {"title_contains": "Main Window"},
                    "anchors": [],
                },
                {
                    "view_id": "dialog",
                    "window_signature": {"title_contains": "Dialog Window"},
                    "anchors": [],
                },
            ],
        }
    )
    dialog = AnchorView.model_validate(
        {
            "view_id": "dialog",
            "window_signature": {"title_contains": "Dialog Window"},
            "anchors": [],
        }
    )

    provider.configure_profile(profile)
    provider._scanner.calls.clear()
    provider.configure_view(dialog)

    assert provider._hwnd == 1002
    assert provider._view is dialog
    assert provider._scanner.calls == []


def test_win32_screen_canvas_click_uses_saved_screen_origin() -> None:
    provider = object.__new__(Win32AutomationProvider)
    provider._user32 = _FakeUser32()
    provider._scanner = _FakeScanner()
    provider._hwnd = 1001
    provider._view = None
    profile = AnchorsContract.model_validate(
        {
            "profile_id": "app",
            "window_signature": {
                "title_contains": "Main Window",
                "screenshot_size": {"width": 400, "height": 300},
                "capture_mode": "screen_canvas",
                "capture_screen_origin_x": 120,
                "capture_screen_origin_y": 80,
            },
            "anchors": [
                {
                    "id": "ok",
                    "action_region": {
                        "pixel": {"x": 10, "y": 20, "width": 30, "height": 40},
                        "normalized": {
                            "x": 0.025,
                            "y": 0.066,
                            "width": 0.075,
                            "height": 0.133,
                        },
                    },
                    "supported_actions": ["click"],
                }
            ],
        }
    )
    provider._profile = profile

    provider._click_anchor(profile.anchors[0])

    assert provider._user32.positions == [(145, 120)]
    assert provider._user32.mouse_events == [0x0002, 0x0004]
