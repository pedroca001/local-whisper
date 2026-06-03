"""Detect the currently focused window and decide if text injection is safe."""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

if sys.platform != "win32":
    raise ImportError("localwhisper.focus requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)

DESKTOP_CLASSES = {
    "Progman",            # Desktop
    "WorkerW",            # Desktop background
    "Shell_TrayWnd",      # Taskbar
}

EDITABLE_CLASS_MARKERS = (
    "edit",
    "richedit",
    "textbox",
    "windowsforms10.edit",
    "prosemirror",
    "contenteditable",
    "ql-editor",
    "cm-content",
    "monaco-editor",
)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def get_foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow())


def get_window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value or 0)


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
    pid = get_window_pid(hwnd)
    if not pid:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
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
    """Return True when the foreground focus looks like an editable text target.

    Order of evidence (strongest first):
    1. Active caret (GUITHREADINFO.hwndCaret) — Windows' canonical "text field
       focused" signal. If the OS reports a caret, we trust it unconditionally.
    2. UIA ControlType / ClassName markers — for Edit, RichEdit, ProseMirror,
       Monaco, contenteditable, etc. Ambiguous results (Pane/Window/Document
       without a text pattern) DO NOT veto; they fall through to Win32.
    3. Win32 ClassName fallback for legacy/native apps.
    """
    hwnd = get_foreground_hwnd()
    if not hwnd:
        log.debug("can_inject: no foreground hwnd")
        return False
    if get_window_pid(hwnd) == os.getpid():
        log.debug("can_inject: foreground belongs to LocalWhisper itself")
        return False
    cls = get_window_class(hwnd)
    if cls in DESKTOP_CLASSES:
        log.debug("can_inject: desktop/taskbar (class=%s)", cls)
        return False

    if _has_active_caret(hwnd):
        log.debug("can_inject: active caret detected for hwnd=%s class=%s", hwnd, cls)
        return True

    uia_result = _uia_focused_control_looks_editable()
    if uia_result is True:
        return True
    if uia_result is False:
        # UIA gave a definitive negative — but we still trust Win32 markers
        # below, because some Electron apps mis-report editable controls.
        log.debug("can_inject: UIA returned False; trying Win32 fallback")

    win32_result = _focused_control_looks_editable(hwnd)
    log.debug("can_inject: Win32 fallback -> %s (hwnd=%s class=%s)", win32_result, hwnd, cls)
    return win32_result


def _has_active_caret(hwnd: int) -> bool:
    """True when the focused thread has an active caret (= text-edit focus)."""
    pid = wintypes.DWORD(0)
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not thread_id:
        return False
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return False
    return bool(info.hwndCaret)


def _uia_focused_control_looks_editable() -> bool | None:
    """Use Windows UI Automation for browser/Electron/modern app edit fields.

    Returns None when UIA is unavailable or ambiguous so callers can fall back
    to the Win32 caret/class detection. We only return False for obviously
    non-editable controls; ambiguous Document/Pane/Window become None.
    """
    try:
        import uiautomation as auto
    except Exception:
        return None

    try:
        control = auto.GetFocusedControl()
    except Exception as e:
        log.debug("can_inject UIA: GetFocusedControl failed: %s", e)
        return None
    if not control:
        log.debug("can_inject UIA: no focused control")
        return None

    control_type = (getattr(control, "ControlTypeName", "") or "").lower()
    class_name = (getattr(control, "ClassName", "") or "").lower()
    log.debug("can_inject UIA: ControlType=%r ClassName=%r", control_type, class_name)

    if any(marker in class_name for marker in EDITABLE_CLASS_MARKERS):
        return True
    if "edit" in control_type or "text" in control_type:
        return True
    if "document" in control_type:
        # Browser contenteditable surfaces here. If GetTextPattern works we
        # trust it; if it errors we leave the decision to the Win32 path.
        try:
            if bool(control.GetTextPattern()):
                return True
        except Exception as e:
            log.debug("can_inject UIA: Document GetTextPattern failed: %s", e)
        return None
    # Pane/Window/etc are inconclusive — don't veto, let Win32 + caret decide.
    return None


def _focused_control_looks_editable(hwnd: int) -> bool:
    pid = wintypes.DWORD(0)
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not thread_id:
        return False

    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    if user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        if info.hwndCaret:
            return True
        focus_hwnd = int(info.hwndFocus or 0)
        if focus_hwnd:
            focus_cls = get_window_class(focus_hwnd).lower()
            if any(marker in focus_cls for marker in EDITABLE_CLASS_MARKERS):
                return True

    cls = get_window_class(hwnd).lower()
    return any(marker in cls for marker in EDITABLE_CLASS_MARKERS)


def get_focus_info() -> dict:
    hwnd = get_foreground_hwnd()
    return {
        "hwnd": hwnd,
        "pid": get_window_pid(hwnd) if hwnd else 0,
        "class": get_window_class(hwnd) if hwnd else "",
        "title": get_window_title(hwnd) if hwnd else "",
        "process": get_process_name(hwnd) if hwnd else "",
        "can_inject": can_inject_text(),
    }


def activate_window(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        if get_window_pid(hwnd) == os.getpid():
            return False
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        ok = bool(user32.SetForegroundWindow(hwnd))
        time.sleep(0.05)
        return ok
    except Exception:
        return False
