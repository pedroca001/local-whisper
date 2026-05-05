from __future__ import annotations

import logging
import sys
import threading
import traceback
from pathlib import Path

from .config import _appdata_dir

LOG_PATH = _appdata_dir() / "localwhisper.log"


def setup_logging() -> Path:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
        force=True,
    )
    logging.getLogger(__name__).info("Logging started: %s", LOG_PATH)

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

    return LOG_PATH


def format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
