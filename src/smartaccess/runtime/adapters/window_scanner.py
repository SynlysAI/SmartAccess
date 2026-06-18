"""基于 Win32 API 的窗口扫描和截图工具。"""

from __future__ import annotations

import ctypes
import platform
import struct
import zlib
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

_IS_WINDOWS = platform.system().lower() == "windows"
_USER32: Any | None = ctypes.windll.user32 if _IS_WINDOWS else None
_GDI32: Any | None = ctypes.windll.gdi32 if _IS_WINDOWS else None
GA_ROOTOWNER = 3
GW_OWNER = 4


@dataclass(slots=True)
class WindowInfo:
    """桌面顶层窗口信息。"""

    title: str
    hwnd: int
    width: int = 0
    height: int = 0

    @property
    def matched(self) -> bool:
        """返回窗口是否匹配扫描条件。"""

        return True


class CaptureErrorReason:
    """窗口截图失败原因。"""

    MINIMIZED = "该窗口已最小化，请先恢复窗口再捕获"
    NO_ACCESS = "无法获取窗口画面：权限不足或被系统保护"
    EMPTY_RECT = "窗口区域无效（尺寸为 0）"
    GDI_FAILED = "GDI 截图失败，窗口可能使用了硬件加速渲染"
    NOT_WINDOWS = "当前系统不支持 Win32 窗口截图"
    UNKNOWN = "截图失败：未知错误"

    @classmethod
    def from_hwnd(cls, hwnd: int) -> str | None:
        """检查截图前置条件。

        Args:
            hwnd: 窗口句柄。

        Returns:
            错误原因；可继续截图时返回 None。
        """

        if _USER32 is None:
            return cls.NOT_WINDOWS
        if _USER32.IsIconic(hwnd):
            return cls.MINIMIZED
        rect = wintypes.RECT()
        if not _USER32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return cls.NO_ACCESS
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return cls.EMPTY_RECT
        return None


class WindowScanner:
    """枚举可见、可用的顶层窗口。"""

    def __init__(self) -> None:
        """初始化窗口扫描器。"""

        _configure_win32_api()

    def scan(
        self,
        *,
        title_contains: str | None = None,
        title_equals: str | None = None,
        min_title_len: int = 1,
        skip_empty_title: bool = True,
        include_disabled: bool = False,
    ) -> list[WindowInfo]:
        """扫描窗口列表。

        Args:
            title_contains: 标题包含（子串）过滤文本。
            title_equals: 标题精确匹配过滤文本（忽略大小写）。
            min_title_len: 最小标题长度。
            skip_empty_title: 是否跳过空标题窗口。
            include_disabled: 是否包含被模态弹窗禁用的宿主窗口。

        Returns:
            窗口信息列表。
        """

        if _USER32 is None:
            return []
        results: list[WindowInfo] = []

        def _callback(hwnd: int, _lparam: int) -> bool:
            if not _USER32.IsWindowVisible(hwnd):
                return True
            if not include_disabled and not _USER32.IsWindowEnabled(hwnd):
                return True
            title = _get_window_title(hwnd)
            if skip_empty_title and not title.strip():
                return True
            if len(title) < min_title_len:
                return True
            if title_contains and title_contains.lower() not in title.lower():
                return True
            if title_equals and title_equals.lower() != title.lower():
                return True
            rect = wintypes.RECT()
            if _USER32.GetClientRect(hwnd, ctypes.byref(rect)):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
            else:
                width, height = 0, 0
            results.append(WindowInfo(title=title, hwnd=hwnd, width=width, height=height))
            return True

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        _USER32.EnumWindows(enum_proc(_callback), 0)
        results.sort(key=lambda item: item.title.lower())
        return results

    def scan_contains(
        self,
        substring: str,
        *,
        include_disabled: bool = False,
    ) -> list[WindowInfo]:
        """扫描标题包含指定文本的窗口。

        Args:
            substring: 标题包含文本。
            include_disabled: 是否包含被模态弹窗禁用的宿主窗口。

        Returns:
            匹配窗口列表。
        """

        return self.scan(title_contains=substring, include_disabled=include_disabled)

    def scan_equals(
        self,
        title: str,
        *,
        include_disabled: bool = False,
    ) -> list[WindowInfo]:
        """扫描标题与指定文本精确相等的窗口（忽略大小写）。

        Args:
            title: 精确匹配的窗口标题。
            include_disabled: 是否包含被模态弹窗禁用的宿主窗口。

        Returns:
            匹配窗口列表。
        """

        return self.scan(title_equals=title, include_disabled=include_disabled)


_LAST_CAPTURE_ERROR = ""
_LAST_CAPTURE_METADATA: dict[str, int] = {
    "origin_x": 0,
    "origin_y": 0,
    "window_x": 0,
    "window_y": 0,
    "offset_x": 0,
    "offset_y": 0,
}


def capture_window(hwnd: int) -> bytes | None:
    """按窗口句柄截取 PNG 图像。

    Args:
        hwnd: 窗口句柄。

    Returns:
        PNG 字节；失败时返回 None。
    """

    global _LAST_CAPTURE_ERROR, _LAST_CAPTURE_METADATA  # noqa: PLW0603
    if _USER32 is None or _GDI32 is None:
        _LAST_CAPTURE_ERROR = CaptureErrorReason.NOT_WINDOWS
        return None
    _configure_win32_api()
    reason = CaptureErrorReason.from_hwnd(hwnd)
    if reason is not None:
        _LAST_CAPTURE_ERROR = reason
        return None
    rect = _capture_bounds(hwnd)
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    window_rect = wintypes.RECT()
    _USER32.GetWindowRect(hwnd, ctypes.byref(window_rect))
    _LAST_CAPTURE_METADATA = {
        "origin_x": int(rect.left),
        "origin_y": int(rect.top),
        "window_x": int(window_rect.left),
        "window_y": int(window_rect.top),
        "offset_x": int(window_rect.left - rect.left),
        "offset_y": int(window_rect.top - rect.top),
    }

    data = _bitblt_window(rect.left, rect.top, width, height)
    if data is None:
        data = _print_window(hwnd, width, height)
    if data is None:
        _LAST_CAPTURE_ERROR = CaptureErrorReason.GDI_FAILED
        return None
    return _raw_to_png(data, width, height)


def capture_error_reason() -> str:
    """返回最近一次截图失败原因。"""

    return _LAST_CAPTURE_ERROR or CaptureErrorReason.UNKNOWN


def capture_metadata() -> dict[str, int]:
    """返回最近一次截图的画布元数据。"""

    return dict(_LAST_CAPTURE_METADATA)


def _capture_bounds(hwnd: int) -> wintypes.RECT:
    """计算截图区域，包含主窗口及其可见弹窗。

    Args:
        hwnd: 主窗口句柄。

    Returns:
        覆盖主窗口和相关弹窗的屏幕矩形。
    """

    rect = wintypes.RECT()
    _USER32.GetWindowRect(hwnd, ctypes.byref(rect))
    bounds = wintypes.RECT(rect.left, rect.top, rect.right, rect.bottom)

    def _callback(candidate_hwnd: int, _lparam: int) -> bool:
        if candidate_hwnd == hwnd:
            return True
        if not _USER32.IsWindowVisible(candidate_hwnd):
            return True
        if not _is_related_popup(hwnd, candidate_hwnd):
            return True
        candidate_rect = wintypes.RECT()
        if not _USER32.GetWindowRect(candidate_hwnd, ctypes.byref(candidate_rect)):
            return True
        if candidate_rect.right <= candidate_rect.left:
            return True
        if candidate_rect.bottom <= candidate_rect.top:
            return True
        bounds.left = min(bounds.left, candidate_rect.left)
        bounds.top = min(bounds.top, candidate_rect.top)
        bounds.right = max(bounds.right, candidate_rect.right)
        bounds.bottom = max(bounds.bottom, candidate_rect.bottom)
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _USER32.EnumWindows(enum_proc(_callback), 0)
    return bounds


def _configure_win32_api() -> None:
    """配置 Win32 API 参数类型。"""

    if _USER32 is None or _GDI32 is None:
        return
    _USER32.EnumWindows.argtypes = (
        ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
        wintypes.LPARAM,
    )
    _USER32.EnumWindows.restype = wintypes.BOOL
    _USER32.IsWindowVisible.argtypes = (wintypes.HWND,)
    _USER32.IsWindowEnabled.argtypes = (wintypes.HWND,)
    _USER32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    _USER32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _USER32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    _USER32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    _USER32.GetWindowDC.argtypes = (wintypes.HWND,)
    _USER32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    _USER32.GetAncestor.restype = wintypes.HWND
    _USER32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
    _USER32.GetWindow.restype = wintypes.HWND
    _USER32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    _USER32.IsIconic.argtypes = (wintypes.HWND,)
    _USER32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
    _GDI32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    _GDI32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
    _GDI32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    _GDI32.DeleteDC.argtypes = (wintypes.HDC,)
    _GDI32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    _GDI32.BitBlt.argtypes = (
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    )


def _get_window_title(hwnd: int) -> str:
    """读取窗口标题。"""

    length = _USER32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    _USER32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value or ""


def _is_related_popup(root_hwnd: int, candidate_hwnd: int) -> bool:
    """判断候选窗口是否属于目标窗口弹窗。

    Args:
        root_hwnd: 主窗口句柄。
        candidate_hwnd: 候选弹窗句柄。

    Returns:
        是否属于同一主窗口的弹窗。
    """

    if _USER32.GetAncestor(candidate_hwnd, GA_ROOTOWNER) == root_hwnd:
        return True
    owner = _USER32.GetWindow(candidate_hwnd, GW_OWNER)
    while owner:
        if owner == root_hwnd:
            return True
        owner = _USER32.GetWindow(owner, GW_OWNER)
    return False


def _print_window(hwnd: int, width: int, height: int) -> bytes | None:
    """使用 PrintWindow 截图。"""

    hdc_screen = _USER32.GetWindowDC(hwnd)
    if not hdc_screen:
        return None
    try:
        hdc_mem = _GDI32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            return None
        bitmap = _GDI32.CreateCompatibleBitmap(hdc_screen, width, height)
        if not bitmap:
            _GDI32.DeleteDC(hdc_mem)
            return None
        old_bmp = _GDI32.SelectObject(hdc_mem, bitmap)
        try:
            if not _USER32.PrintWindow(hwnd, hdc_mem, 2):
                return None
            return _dib_from_bitmap(hdc_mem, bitmap, width, height)
        finally:
            _GDI32.SelectObject(hdc_mem, old_bmp)
            _GDI32.DeleteObject(bitmap)
            _GDI32.DeleteDC(hdc_mem)
    finally:
        _USER32.ReleaseDC(hwnd, hdc_screen)


def _bitblt_window(x: int, y: int, width: int, height: int) -> bytes | None:
    """使用屏幕 BitBlt 兜底截图。"""

    hdc_screen = _USER32.GetDC(0)
    if not hdc_screen:
        return None
    try:
        hdc_mem = _GDI32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            return None
        bitmap = _GDI32.CreateCompatibleBitmap(hdc_screen, width, height)
        if not bitmap:
            _GDI32.DeleteDC(hdc_mem)
            return None
        old_bmp = _GDI32.SelectObject(hdc_mem, bitmap)
        try:
            if not _GDI32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, x, y, 0x00CC0020):
                return None
            return _dib_from_bitmap(hdc_mem, bitmap, width, height)
        finally:
            _GDI32.SelectObject(hdc_mem, old_bmp)
            _GDI32.DeleteObject(bitmap)
            _GDI32.DeleteDC(hdc_mem)
    finally:
        _USER32.ReleaseDC(0, hdc_screen)


def _dib_from_bitmap(hdc_mem: int, bitmap: int, width: int, height: int) -> bytes:
    """从 GDI 位图中提取 BGRA 原始像素。"""

    class _BitmapInfoHeader(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bmp_info = _BitmapInfoHeader()
    bmp_info.biSize = ctypes.sizeof(_BitmapInfoHeader)
    bmp_info.biWidth = width
    bmp_info.biHeight = -height
    bmp_info.biPlanes = 1
    bmp_info.biBitCount = 32
    bmp_info.biCompression = 0
    buffer_size = width * height * 4
    buffer = (ctypes.c_byte * buffer_size)()
    _GDI32.GetDIBits.argtypes = (
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(_BitmapInfoHeader),
        wintypes.UINT,
    )
    _GDI32.GetDIBits(hdc_mem, bitmap, 0, height, buffer, ctypes.byref(bmp_info), 0)
    return bytes(buffer)


def _raw_to_png(raw_bgra: bytes, width: int, height: int) -> bytes:
    """把 BGRA 原始像素编码成 PNG。"""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + chunk
            + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        )

    raw_lines: list[bytes] = []
    for row_idx in range(height):
        row = bytearray(b"\x00")
        offset = row_idx * width * 4
        for col in range(width):
            base = offset + col * 4
            row.extend(
                struct.pack(
                    "BBBB",
                    raw_bgra[base + 2],
                    raw_bgra[base + 1],
                    raw_bgra[base],
                    raw_bgra[base + 3],
                )
            )
        raw_lines.append(bytes(row))
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    image_data = zlib.compress(b"".join(raw_lines))
    return signature + _chunk(b"IHDR", header) + _chunk(b"IDAT", image_data) + _chunk(b"IEND", b"")
