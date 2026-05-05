"""Detect the currently focused window and decide if text injection is safe."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":
    raise ImportError("localwhisper.focus requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)

DESKTOP_CLASSES = {
    "Progman",            # Desktop
    "WorkerW",            # Desktop background
    "Shell_TrayWnd",      # Taskbar
}


def get_foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow())


def get_window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, buf, length)
    return buf.value


def get_process_name(hwnd: int) -> str:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            path = buf.value
            return path.rsplit("\\", 1)[-1] if path else ""
    finally:
        kernel32.CloseHandle(h)
    return ""


def can_inject_text() -> bool:
    """Return True if the current foreground window is likely a text-accepting app.

    Conservative heuristic: returns False only for desktop / taskbar shells.
    Everything else (Notepad, Chrome, VSCode, Slack, Word, Discord) gets injection.
    """
    hwnd = get_foreground_hwnd()
    if not hwnd:
        return False
    cls = get_window_class(hwnd)
    if cls in DESKTOP_CLASSES:
        return False
    return True


def get_focus_info() -> dict:
    hwnd = get_foreground_hwnd()
    return {
        "hwnd": hwnd,
        "class": get_window_class(hwnd) if hwnd else "",
        "title": get_window_title(hwnd) if hwnd else "",
        "process": get_process_name(hwnd) if hwnd else "",
        "can_inject": can_inject_text(),
    }
