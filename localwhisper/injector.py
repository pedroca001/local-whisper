"""Win32 SendInput-based Unicode text injector.

Sends typed characters to the currently focused window as if the user typed
them, with proper handling of Portuguese accented characters (ç, ã, õ, é).
"""
from __future__ import annotations

import ctypes
import dataclasses
import sys
import time
from ctypes import wintypes

if sys.platform != "win32":
    raise ImportError("localwhisper.injector requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
EM_REPLACESEL = 0x00C2
SMTO_ABORTIFHUNG = 0x0002

HISTORY_EXCLUDE_FORMAT = "ExcludeClipboardContentFromMonitorProcessing"
HISTORY_INCLUDE_FORMAT = "CanIncludeInClipboardHistory"
CLOUD_UPLOAD_FORMAT = "CanUploadToCloudClipboard"

WIN32_REPLACESEL_CLASS_MARKERS = (
    "edit",
    "richedit",
    "richeditd2d",
    "windowsforms10.edit",
)

ULONG_PTR = ctypes.c_size_t
DWORD_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.SendMessageTimeoutW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(DWORD_PTR),
)
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = ()
user32.EmptyClipboard.restype = wintypes.BOOL
user32.EnumClipboardFormats.argtypes = (wintypes.UINT,)
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.IsClipboardFormatAvailable.argtypes = (wintypes.UINT,)
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalSize.restype = ctypes.c_size_t


@dataclasses.dataclass(frozen=True)
class ClipboardFormatData:
    fmt: int
    data: bytes


@dataclasses.dataclass(frozen=True)
class ClipboardSnapshot:
    formats: tuple[ClipboardFormatData, ...]


def _make_unicode_input(code_unit: int, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(
        wVk=0,
        wScan=code_unit,
        dwFlags=flags,
        time=0,
        dwExtraInfo=0,
    )
    return inp


def _make_vk_input(vk: int, key_up: bool = False) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=KEYEVENTF_KEYUP if key_up else 0,
        time=0,
        dwExtraInfo=0,
    )
    return inp


def _window_class(hwnd: int) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def can_replace_selection_with_message(hwnd: int) -> bool:
    """True for Win32 edit controls that accept EM_REPLACESEL."""
    cls = _window_class(hwnd).lower()
    return bool(cls) and any(marker in cls for marker in WIN32_REPLACESEL_CLASS_MARKERS)


def replace_selection_with_message(hwnd: int, text: str, timeout_ms: int = 300) -> bool:
    """Insert text into a native edit/RichEdit control without touching clipboard."""
    if not hwnd or not text or not can_replace_selection_with_message(hwnd):
        return False
    buf = ctypes.create_unicode_buffer(text)
    result = DWORD_PTR(0)
    delivered = user32.SendMessageTimeoutW(
        hwnd,
        EM_REPLACESEL,
        1,
        ctypes.cast(buf, ctypes.c_void_p).value,
        SMTO_ABORTIFHUNG,
        int(timeout_ms),
        ctypes.byref(result),
    )
    return bool(delivered)


def type_unicode(text: str, batch: int = 32) -> int:
    """Send `text` to the foreground window as Unicode keystrokes.

    Returns number of code units injected. Handles BMP + surrogate pairs
    (emoji) automatically because Python str iteration yields code points
    that we re-encode to UTF-16 code units.
    """
    if not text:
        return 0

    utf16 = text.encode("utf-16-le")
    code_units = [int.from_bytes(utf16[i : i + 2], "little") for i in range(0, len(utf16), 2)]

    sent_total = 0
    i = 0
    while i < len(code_units):
        chunk = code_units[i : i + batch]
        inputs = (INPUT * (2 * len(chunk)))()
        for j, cu in enumerate(chunk):
            inputs[2 * j] = _make_unicode_input(cu, key_up=False)
            inputs[2 * j + 1] = _make_unicode_input(cu, key_up=True)
        n = user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT))
        sent_total += n
        i += batch
    return sent_total


def _open_clipboard_with_retry(timeout_s: float = 0.5) -> bool:
    deadline = time.time() + timeout_s
    while time.time() <= deadline:
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.025)
    return bool(user32.OpenClipboard(None))


def _read_global_bytes(handle: int) -> bytes | None:
    if not handle:
        return None
    size = int(kernel32.GlobalSize(handle))
    if size <= 0:
        return None
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(handle)


def _alloc_global_bytes(data: bytes) -> int:
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        ctypes.memmove(ptr, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)
    return int(handle)


def _text_to_clipboard_bytes(text: str) -> bytes:
    return text.encode("utf-16-le") + b"\x00\x00"


def _dword_clipboard_bytes(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=False)


def _registered_clipboard_format(name: str) -> int:
    fmt = user32.RegisterClipboardFormatW(name)
    if not fmt:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(fmt)


def _set_clipboard_format(fmt: int, data: bytes) -> None:
    handle = _alloc_global_bytes(data)
    if not user32.SetClipboardData(fmt, handle):
        raise ctypes.WinError(ctypes.get_last_error())


def _set_history_exclusion_formats() -> None:
    _set_clipboard_format(_registered_clipboard_format(HISTORY_EXCLUDE_FORMAT), b"\x00")
    _set_clipboard_format(_registered_clipboard_format(HISTORY_INCLUDE_FORMAT), _dword_clipboard_bytes(0))
    _set_clipboard_format(_registered_clipboard_format(CLOUD_UPLOAD_FORMAT), _dword_clipboard_bytes(0))


def snapshot_clipboard() -> ClipboardSnapshot | None:
    """Best-effort copy of current HGLOBAL clipboard formats."""
    if not _open_clipboard_with_retry():
        return None
    try:
        formats: list[ClipboardFormatData] = []
        fmt = 0
        while True:
            fmt = int(user32.EnumClipboardFormats(fmt))
            if not fmt:
                break
            handle = user32.GetClipboardData(fmt)
            data = _read_global_bytes(handle)
            if data is not None:
                formats.append(ClipboardFormatData(fmt=fmt, data=data))
        return ClipboardSnapshot(tuple(formats))
    finally:
        user32.CloseClipboard()


def current_clipboard_text() -> str:
    if not _open_clipboard_with_retry():
        return ""
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        data = _read_global_bytes(user32.GetClipboardData(CF_UNICODETEXT))
        if not data:
            return ""
        return data.decode("utf-16-le", errors="ignore").rstrip("\x00")
    finally:
        user32.CloseClipboard()


def set_clipboard_text_protected(text: str) -> None:
    """Set Unicode text while asking Windows not to add it to clipboard history."""
    if not _open_clipboard_with_retry():
        raise RuntimeError("Could not open clipboard.")
    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        _set_clipboard_format(CF_UNICODETEXT, _text_to_clipboard_bytes(text))
        _set_history_exclusion_formats()
    finally:
        user32.CloseClipboard()


def restore_clipboard(snapshot: ClipboardSnapshot | None) -> None:
    """Restore a prior snapshot without creating a new clipboard-history item."""
    if not _open_clipboard_with_retry():
        return
    try:
        if not user32.EmptyClipboard():
            return
        if snapshot:
            for item in snapshot.formats:
                try:
                    _set_clipboard_format(item.fmt, item.data)
                except Exception:
                    pass
        _set_history_exclusion_formats()
    finally:
        user32.CloseClipboard()


def _send_input_events(events: list[INPUT]) -> int:
    inputs = (INPUT * len(events))()
    for i, event in enumerate(events):
        inputs[i] = event
    return int(user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT)))


def paste_clipboard_hotkey(delay_s: float = 0.025) -> int:
    """Send Ctrl+V with small pauses so Chromium/Electron fields accept it."""
    if delay_s <= 0:
        return _send_input_events(
            [
                _make_vk_input(VK_CONTROL, key_up=False),
                _make_vk_input(VK_V, key_up=False),
                _make_vk_input(VK_V, key_up=True),
                _make_vk_input(VK_CONTROL, key_up=True),
            ]
        )

    sent = 0
    sent += _send_input_events([_make_vk_input(VK_CONTROL, key_up=False)])
    time.sleep(delay_s)
    sent += _send_input_events([_make_vk_input(VK_V, key_up=False), _make_vk_input(VK_V, key_up=True)])
    time.sleep(delay_s)
    sent += _send_input_events([_make_vk_input(VK_CONTROL, key_up=True)])
    return sent


def release_modifiers() -> int:
    """Send key-up for Win/Alt/Ctrl/Shift so a held global-hotkey combination
    does not bleed into a subsequent synthetic keystroke (e.g. a still-held
    Win key turning Ctrl+V into Win+V / clipboard history)."""
    keys = (VK_LWIN, VK_RWIN, VK_MENU, VK_CONTROL, VK_SHIFT)
    inputs = (INPUT * len(keys))()
    for i, vk in enumerate(keys):
        inputs[i] = _make_vk_input(vk, key_up=True)
    return int(user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT)))
