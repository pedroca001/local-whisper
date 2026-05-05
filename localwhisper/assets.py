"""Helpers for locating bundled LocalWhisper image assets."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


APP_ICON_FILES = (
    "icon.ico",
    "icon.png",
    "128x128@2x.png",
    "128x128.png",
    "64x64.png",
    "32x32.png",
)

TRAY_ICON_STATES = {
    "ready": "Ready",
    "recording": "Recording",
    "processing": "Processing",
    "complete": "Complete",
}


def _candidate_icon_dirs() -> tuple[Path, ...]:
    package_dir = Path(__file__).resolve().parent
    project_dir = package_dir.parent
    dirs: list[Path] = []

    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", project_dir))
        dirs.append(bundle_dir / "icons")

    dirs.extend(
        [
            project_dir / "icons",
            package_dir / "resources" / "icons",
            Path.cwd() / "icons",
        ]
    )

    seen: set[Path] = set()
    unique_dirs: list[Path] = []
    for path in dirs:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_dirs.append(path)
    return tuple(unique_dirs)


def icons_dir() -> Path:
    for path in _candidate_icon_dirs():
        if path.exists():
            return path
    return _candidate_icon_dirs()[0]


def app_icon_paths() -> list[Path]:
    base = icons_dir()
    return [base / name for name in APP_ICON_FILES if (base / name).exists()]


def tray_icon_path(state: str, *, dark_taskbar: bool) -> Path:
    base_name = TRAY_ICON_STATES.get(state.lower(), state)
    tray_dir = icons_dir() / "tray-icons"
    names = (
        f"{base_name}-1.png",
        f"{base_name}.png",
    ) if dark_taskbar else (
        f"{base_name}.png",
        f"{base_name}-1.png",
    )

    for name in names:
        path = tray_dir / name
        if path.exists():
            return path
    raise FileNotFoundError(f"Tray icon not found for state: {state}")


def load_tray_icon(state: str, *, dark_taskbar: bool) -> Image.Image:
    with Image.open(tray_icon_path(state, dark_taskbar=dark_taskbar)) as img:
        return img.convert("RGBA")
