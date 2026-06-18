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
