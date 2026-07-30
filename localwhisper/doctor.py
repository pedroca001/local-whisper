"""Read-only health checks used by the UI, CLI and support bundles."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
from pathlib import Path

from .config import config_path, history_db_path, models_dir_path
from .diagnostics import redact_support_value, system_summary


def _module_status(name: str) -> dict:
    spec = importlib.util.find_spec(name)
    return {"available": spec is not None}


def _destination_writable(path: Path) -> bool:
    candidate = path if path.exists() and path.is_dir() else path.parent
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.exists() and os.access(candidate, os.W_OK)


def run_doctor() -> dict:
    summary = system_summary()
    checks: dict[str, dict] = {}

    config = config_path()
    config_ok = not config.exists() and _destination_writable(config)
    config_error = ""
    raw_config: dict = {}
    try:
        if config.exists():
            raw_config = json.loads(config.read_text(encoding="utf-8"))
            config_ok = isinstance(raw_config, dict)
    except Exception as exc:
        config_error = str(exc)
    models_dir = Path(str(raw_config.get("models_dir") or models_dir_path()))
    checks["models_dir"] = {
        "ok": models_dir.is_dir() or _destination_writable(models_dir),
        "path": str(models_dir),
    }
    checks["config"] = {
        "ok": config_ok,
        "path": str(config),
        "error": config_error,
    }

    db = history_db_path()
    db_ok = not db.exists() and _destination_writable(db)
    db_error = ""
    try:
        if db.exists():
            with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
                result = conn.execute("PRAGMA quick_check").fetchone()
            db_ok = bool(result and result[0] == "ok")
    except Exception as exc:
        db_error = str(exc)
    checks["history"] = {
        "ok": db_ok,
        "path": str(history_db_path()),
        "error": db_error,
    }

    checks["ffmpeg"] = {
        "ok": shutil.which("ffmpeg") is not None or _module_status("imageio_ffmpeg")["available"],
        "path": shutil.which("ffmpeg") or "imageio-ffmpeg",
    }
    checks["dependencies"] = {
        name: _module_status(name)
        for name in ("numpy", "sounddevice", "faster_whisper", "PySide6", "pystray")
    }

    cuda_count = 0
    cuda_error = ""
    try:
        import ctranslate2

        cuda_count = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:
        cuda_error = str(exc)
    checks["cuda"] = {
        "ok": cuda_count > 0,
        "device_count": cuda_count,
        "error": cuda_error,
    }

    required_ok = (
        checks["config"]["ok"]
        and checks["history"]["ok"]
        and all(item["available"] for item in checks["dependencies"].values())
    )
    return redact_support_value({
        "ok": required_ok,
        "summary": summary,
        "checks": checks,
    })
