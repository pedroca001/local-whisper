from __future__ import annotations

import logging
import os
import platform
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import _local_appdata_dir


def log_path() -> Path:
    return _local_appdata_dir() / "localwhisper.log"


LOG_PATH = log_path()


def setup_logging() -> Path:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            path,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    ]
    if sys.stdout is not None and not getattr(sys, "frozen", False):
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger(__name__).info("Logging started: %s", path)

    def excepthook(exc_type, exc_value, exc_tb):
        logging.critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        old_threading_hook = threading.excepthook

        def thread_excepthook(args):
            logging.critical(
                "Unhandled thread exception in %s",
                getattr(args.thread, "name", "<unknown>"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            old_threading_hook(args)

        threading.excepthook = thread_excepthook

    return path


def format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def system_summary() -> dict:
    """Return a redacted, support-friendly runtime summary."""
    from . import __version__
    from .config import config_path, history_db_path, models_dir_path

    local_data = _local_appdata_dir()
    writable_probe = local_data
    while not writable_probe.exists() and writable_probe != writable_probe.parent:
        writable_probe = writable_probe.parent
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "config_path": str(config_path()),
        "history_db": str(history_db_path()),
        "models_dir": str(models_dir_path()),
        "log_path": str(log_path()),
        "appdata_writable": writable_probe.exists() and os.access(writable_probe, os.W_OK),
    }
