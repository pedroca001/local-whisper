"""LocalWhisper entry point.

Usage:
    python run.py
    python run.py record --duration 5
    python run.py transcribe meeting.mp4 --format srt -o meeting.srt
    python run.py doctor --json
"""
# ruff: noqa: E402,I001
from __future__ import annotations

import os
import sys

# Under pythonw.exe (no console), sys.stdout / sys.stderr are None. Redirect
# before importing anything that may write during import.
if sys.stdout is None or sys.stderr is None:
    _log_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "LocalWhisper",
    )
    os.makedirs(_log_dir, exist_ok=True)
    sys.stdout = open(
        os.path.join(_log_dir, "app.log"),
        "a",
        encoding="utf-8",
        buffering=1,
    )
    sys.stderr = open(
        os.path.join(_log_dir, "app.log.err"),
        "a",
        encoding="utf-8",
        buffering=1,
    )

# PySide6's import hook can inspect six.moves and trigger CPython's module repr
# code, which expects this otherwise-missing loader attribute.
try:
    import six as _six

    if not hasattr(_six._SixMetaPathImporter, "_path"):
        _six._SixMetaPathImporter._path = None
except Exception:
    pass

from localwhisper.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
