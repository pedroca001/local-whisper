"""System tray icon with state-aware visual feedback.

States:
    ready       — idle, ready for hotkey
    recording   — actively capturing audio (red dot)
    processing  — finalizing transcription (blue dot)
    complete    — just finished successfully (green dot, ~1s flash)

Auto-detects Windows light/dark taskbar theme so the icon stays visible.
"""
from __future__ import annotations

import sys
import threading
from typing import Callable, Optional

import pystray

from .assets import load_tray_icon


def _is_taskbar_dark() -> bool:
    """Check Windows taskbar theme. Returns True if dark mode (use light icons)."""
    if sys.platform != "win32":
        return True
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            # `SystemUsesLightTheme` controls the taskbar/start menu
            value, _ = winreg.QueryValueEx(k, "SystemUsesLightTheme")
            return value == 0
    except Exception:
        return True  # default: assume dark taskbar


class TrayIcon:
    def __init__(
        self,
        on_settings: Callable[[], None],
        on_record: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self.on_settings = on_settings
        self.on_record = on_record
        self.on_quit = on_quit
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        dark_taskbar = _is_taskbar_dark()
        self._states = {
            "ready": load_tray_icon("ready", dark_taskbar=dark_taskbar),
            "recording": load_tray_icon("recording", dark_taskbar=dark_taskbar),
            "processing": load_tray_icon("processing", dark_taskbar=dark_taskbar),
            "complete": load_tray_icon("complete", dark_taskbar=dark_taskbar),
        }
        self._state = "ready"
        self._complete_timer: Optional[threading.Timer] = None

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Settings…", lambda *_: self.on_settings(), default=True),
            pystray.MenuItem("Record manually", lambda *_: self.on_record()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda *_: self._quit()),
        )

    def start(self) -> None:
        self._icon = pystray.Icon(
            "LocalWhisper",
            self._states["ready"],
            "LocalWhisper",
            self._build_menu(),
        )
        self._thread = threading.Thread(target=self._icon.run, name="TrayThread", daemon=True)
        self._thread.start()

    def set_state(self, state: str) -> None:
        if state not in self._states:
            return
        self._state = state
        if self._icon:
            try:
                self._icon.icon = self._states[state]
                self._icon.title = f"LocalWhisper — {state.capitalize()}"
            except Exception:
                pass

    # Compat with old API: set_active(True) -> recording, False -> ready
    def set_active(self, active: bool) -> None:
        self.set_state("recording" if active else "ready")

    def flash_complete(self, hold_seconds: float = 1.2) -> None:
        """Show 'complete' briefly then return to 'ready'."""
        self.set_state("complete")
        if self._complete_timer:
            self._complete_timer.cancel()
        self._complete_timer = threading.Timer(hold_seconds, lambda: self.set_state("ready"))
        self._complete_timer.daemon = True
        self._complete_timer.start()

    def _quit(self) -> None:
        try:
            if self._icon:
                self._icon.stop()
        finally:
            self.on_quit()

    def stop(self) -> None:
        try:
            if self._icon:
                self._icon.stop()
        except Exception:
            pass
