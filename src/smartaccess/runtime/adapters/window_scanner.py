"""Real Windows window scanner via Win32 API (user32.dll).

Zero-dependency window enumeration — usable on any Windows machine without
installing pywinauto. The :class:`WindowScanner` is callable from anywhere;
:class:`RealWindowDiscovery` wraps it as a drop-in replacement for the
stub's ``discover_windows`` return.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Win32 API bindings
# --------------------------------------------------------------------------- #
user32 = ctypes.windll.user32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowEnabled.argtypes = (wintypes.HWND,)
user32.IsWindowEnabled.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetClientRect.restype = wintypes.BOOL


@dataclass(slots=True)
class WindowInfo:
    """A top-level visible window discovered on the desktop."""

    title: str
    hwnd: int
    width: int = 0
    height: int = 0

    @property
    def matched(self) -> bool:
        return True


class WindowScanner:
    """Enumerate visible, enabled top-level windows via ``EnumWindows``.

    Usage::

        scanner = WindowScanner()
        windows = scanner.scan()                # all visible windows
        matches = scanner.scan_contains("微信")  # filter by title substring
    """

    def scan(
        self,
        *,
        title_contains: str | None = None,
        min_title_len: int = 1,
        skip_empty_title: bool = True,
    ) -> list[WindowInfo]:
        """Return visible, enabled top-level windows ordered by title."""

        results: list[WindowInfo] = []

        def _callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            if not user32.IsWindowEnabled(hwnd):
                return True

            title = _get_window_title(hwnd)
            if skip_empty_title and not title.strip():
                return True
            if len(title) < min_title_len:
                return True
            if title_contains and title_contains.lower() not in title.lower():
                return True

            rect = wintypes.RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(rect)):
                w = rect.right - rect.left
                h = rect.bottom - rect.top
            else:
                w, h = 0, 0

            results.append(WindowInfo(title=title, hwnd=hwnd, width=w, height=h))
            return True

        user32.EnumWindows(WNDENUMPROC(_callback), 0)
        results.sort(key=lambda wi: wi.title.lower())
        return results

    def scan_contains(self, substring: str) -> list[WindowInfo]:
        """Shortcut: only windows whose title contains ``substring``."""

        return self.scan(title_contains=substring)


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value or ""


# --------------------------------------------------------------------------- #
# Window screenshot via GDI (zero extra dependencies)
# --------------------------------------------------------------------------- #
gdi32 = ctypes.windll.gdi32
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = (
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
)
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteObject.restype = wintypes.BOOL

user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowDC.argtypes = (wintypes.HWND,)
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.ReleaseDC.restype = ctypes.c_int
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = (
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
)
user32.SetWindowPos.restype = wintypes.BOOL
user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
user32.PrintWindow.restype = wintypes.BOOL

PW_RENDERFULLCONTENT = 2
SRCCOPY = 0x00CC0020
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)


class CaptureErrorReason:
    """Human-readable reasons for capture failure (used by UI for user feedback)."""

    MINIMIZED = "该窗口已最小化，请先恢复窗口再捕获"
    NO_ACCESS = "无法获取窗口画面：权限不足或被系统保护"
    EMPTY_RECT = "窗口区域无效（尺寸为 0）"
    GDI_FAILED = "GDI 截图失败，窗口可能使用了硬件加速渲染"
    UNKNOWN = "截图失败：未知错误"

    @classmethod
    def from_hwnd(cls, hwnd: int) -> str | None:
        """Check preconditions; return an error reason or None if capture may proceed."""

        if user32.IsIconic(hwnd):
            return cls.MINIMIZED
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return cls.NO_ACCESS
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return cls.EMPTY_RECT
        return None


def capture_window(hwnd: int) -> bytes | None:
    """Capture a window as PNG bytes using GDI (PrintWindow + BitBlt fallback).

    Returns ``None`` when the window can't be captured, along with a reason
    accessible via :func:`capture_error_reason`. The caller should show
    a user-facing error message.
    """

    global _last_capture_error  # noqa: PLW0603
    reason = CaptureErrorReason.from_hwnd(hwnd)
    if reason is not None:
        _last_capture_error = reason
        return None

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    # Try PrintWindow first (works for most modern Windows apps).
    data = _print_window(hwnd, w, h)
    if data is None:
        # Fallback: BitBlt from screen DC (works for older / GDI-rendered windows).
        data = _bitblt_window(hwnd, rect.left, rect.top, w, h)
    if data is None:
        _last_capture_error = CaptureErrorReason.GDI_FAILED
        return None

    return _raw_to_png(data, w, h)


_last_capture_error: str = ""


def capture_error_reason() -> str:
    """Return the last capture failure reason (for UI display)."""

    return _last_capture_error or CaptureErrorReason.UNKNOWN


# --------------------------------------------------------------------------- #
# Internal capture helpers
# --------------------------------------------------------------------------- #
def _print_window(hwnd: int, w: int, h: int) -> bytes | None:
    """Use ``PrintWindow`` (works for most apps including Chromium-based ones)."""

    hdc_screen = user32.GetWindowDC(hwnd)
    if not hdc_screen:
        return None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            return None
        bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        if not bitmap:
            gdi32.DeleteDC(hdc_mem)
            return None
        old_bmp = gdi32.SelectObject(hdc_mem, bitmap)
        ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
        if not ok:
            gdi32.SelectObject(hdc_mem, old_bmp)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(hdc_mem)
            return None
        data = _dib_from_bitmap(hdc_mem, bitmap, w, h)
        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(hdc_mem)
        return data
    finally:
        user32.ReleaseDC(hwnd, hdc_screen)


def _bitblt_window(hwnd: int, x: int, y: int, w: int, h: int) -> bytes | None:
    """Fallback: screen-level BitBlt at the window's rect."""

    hdc_screen = user32.GetDC(0)  # entire screen
    if not hdc_screen:
        return None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            return None
        bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        if not bitmap:
            gdi32.DeleteDC(hdc_mem)
            return None
        old_bmp = gdi32.SelectObject(hdc_mem, bitmap)
        ok = gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY)
        if not ok:
            gdi32.SelectObject(hdc_mem, old_bmp)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(hdc_mem)
            return None
        data = _dib_from_bitmap(hdc_mem, bitmap, w, h)
        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(hdc_mem)
        return data
    finally:
        user32.ReleaseDC(0, hdc_screen)


def _dib_from_bitmap(hdc_mem: int, bitmap: int, w: int, h: int) -> bytes:
    """Extract raw BGRA pixel data from a GDI bitmap via GetDIBits."""

    import struct as _struct
    class _BITMAPINFOHEADER(ctypes.Structure):  # noqa: N801
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]
    bmp_info = _BITMAPINFOHEADER()
    bmp_info.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmp_info.biWidth = w
    bmp_info.biHeight = -h  # negative = top-down
    bmp_info.biPlanes = 1
    bmp_info.biBitCount = 32
    bmp_info.biCompression = 0  # BI_RGB
    buf_size = w * h * 4
    buf = (ctypes.c_byte * buf_size)()
    gdi32.GetDIBits.argtypes = (
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.POINTER(_BITMAPINFOHEADER), wintypes.UINT,
    )
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.GetDIBits(hdc_mem, bitmap, 0, h, buf, ctypes.byref(bmp_info), 0)
    return bytes(buf)


def _raw_to_png(raw_bgra: bytes, w: int, h: int) -> bytes:
    """Encode raw BGRA pixels as PNG bytes (pure Python, zero deps)."""

    import struct as _struct
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        return (
            _struct.pack(">I", len(data))
            + chunk
            + _struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    raw_lines: list[bytes] = []
    for row_idx in range(h):
        raw_lines.append(b"\x00")  # filter None
        offset = row_idx * w * 4
        for col in range(w):
            base = offset + col * 4
            b_val = raw_bgra[base]
            g_val = raw_bgra[base + 1]
            r_val = raw_bgra[base + 2]
            a_val = raw_bgra[base + 3]
            raw_lines[-1] += _struct.pack("BBBB", r_val, g_val, b_val, a_val)
    idat = zlib.compress(b"".join(raw_lines))
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
