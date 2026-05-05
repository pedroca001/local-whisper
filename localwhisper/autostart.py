"""Windows registry-based auto-launch toggle (HKCU\\...\\Run)."""
from __future__ import annotations

import sys

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LocalWhisper"


def set_auto_launch(enable: bool, exe_path: str | None = None) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False

    if exe_path is None:
        exe_path = f'"{sys.executable}" "{sys.argv[0]}"'

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False
