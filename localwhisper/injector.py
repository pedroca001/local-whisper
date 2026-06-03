"""Win32 SendInput-based Unicode text injector.

Sends typed characters to the currently focused window as if the user typed
them, with proper handling of Portuguese accented characters (ç, ã, õ, é).
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":
    raise ImportError("localwhisper.injector requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56

ULONG_PTR = ctypes.c_size_t


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


def paste_clipboard_hotkey() -> int:
    inputs = (INPUT * 4)()
    inputs[0] = _make_vk_input(VK_CONTROL, key_up=False)
    inputs[1] = _make_vk_input(VK_V, key_up=False)
    inputs[2] = _make_vk_input(VK_V, key_up=True)
    inputs[3] = _make_vk_input(VK_CONTROL, key_up=True)
    return int(user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT)))
