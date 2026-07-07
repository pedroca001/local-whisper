"""Small, testable decisions for text insertion."""
from __future__ import annotations

CLIPBOARD_TARGET_MARKERS = (
    "code.exe",
    "windowsterminal.exe",
    "wt.exe",
    "terminal",
    "powershell",
    "cmd.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "electron",
    "slack.exe",
    "discord.exe",
    "teams.exe",
)

CLIPBOARD_PASTE_EVENTS = 4


def target_prefers_clipboard(process_name: str | None, window_title: str | None) -> bool:
    """Return True for apps where clipboard paste is more reliable than unicode keys."""
    haystack = f"{process_name or ''}\n{window_title or ''}".lower()
    return any(marker in haystack for marker in CLIPBOARD_TARGET_MARKERS)


def input_events_succeeded(sent_events: int, *, via_clipboard: bool) -> bool:
    """Interpret SendInput counts consistently for typing and paste attempts."""
    expected = CLIPBOARD_PASTE_EVENTS if via_clipboard else 1
    return int(sent_events or 0) >= expected
