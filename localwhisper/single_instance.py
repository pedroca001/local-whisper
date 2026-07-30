"""Windows named-mutex guard preventing duplicate tray/hotkey instances."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self, name: str = r"Local\LocalWhisper.Singleton.v1"):
        self.name = name
        self.handle: int = 0
        self.acquired = False

    def acquire(self) -> bool:
        if self.acquired:
            return True
        if sys.platform != "win32":
            self.acquired = True
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise ctypes.WinError()
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self.handle = int(handle)
        self.acquired = True
        return True

    def release(self) -> None:
        if self.handle and sys.platform == "win32":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle(self.handle)
        self.handle = 0
        self.acquired = False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Another LocalWhisper instance is already running.")
        return self

    def __exit__(self, *_args):
        self.release()
