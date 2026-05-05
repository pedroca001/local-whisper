"""Global hotkey manager using Win32 RegisterHotKey.

Runs a dedicated thread with a Windows message loop. When the registered
hotkey fires, it invokes a Python callback. Supports unregister + re-register
with arbitrary modifier+key combinations.
"""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from typing import Callable, Optional

if sys.platform != "win32":
    raise ImportError("localwhisper.hotkey requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Modifier flags
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

PM_REMOVE = 0x0001

# Virtual-key codes for common keys
VK_CODES: dict[str, int] = {
    "space": 0x20,
    "esc": 0x1B,
    "escape": 0x1B,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
for c in "abcdefghijklmnopqrstuvwxyz":
    VK_CODES[c] = ord(c.upper())
for d in "0123456789":
    VK_CODES[d] = ord(d)


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Parse a string like 'ctrl+space' or 'ctrl+alt+space' into (mods, vk)."""
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    mods = 0
    key: Optional[int] = None
    for p in parts:
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "alt":
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p in ("win", "super", "meta"):
            mods |= MOD_WIN
        else:
            if p not in VK_CODES:
                raise ValueError(f"Unknown key in hotkey: {p!r}")
            key = VK_CODES[p]
    if key is None:
        raise ValueError(f"Hotkey {spec!r} missing a non-modifier key")
    return mods | MOD_NOREPEAT, key


class HotkeyManager:
    """Registers a global hotkey on Windows. Calls `callback` on press."""

    def __init__(self, hotkey: str, callback: Callable[[], None]):
        self.hotkey = hotkey
        self.callback = callback
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._registered = False
        self._registration_error: Optional[str] = None
        self._ready = threading.Event()
        self._stop = threading.Event()

    @property
    def registered(self) -> bool:
        return self._registered

    @property
    def error(self) -> Optional[str]:
        return self._registration_error

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return self._registered
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="HotkeyThread", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._registered

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None
        self._registered = False

    def change(self, hotkey: str) -> bool:
        self.stop()
        self.hotkey = hotkey
        return self.start()

    def _run(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread_id = kernel32.GetCurrentThreadId()

        try:
            mods, vk = parse_hotkey(self.hotkey)
        except Exception as e:
            self._registration_error = f"Parse error: {e}"
            self._registered = False
            self._ready.set()
            return

        hotkey_id = 1
        ok = user32.RegisterHotKey(None, hotkey_id, mods, vk)
        if not ok:
            err = ctypes.get_last_error()
            self._registration_error = f"RegisterHotKey failed (error {err}). Hotkey may be in use."
            self._registered = False
            self._ready.set()
            return

        self._registered = True
        self._registration_error = None
        self._ready.set()

        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:
                        import traceback

                        traceback.print_exc()
        finally:
            user32.UnregisterHotKey(None, hotkey_id)
            self._registered = False
