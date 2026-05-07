"""LocalWhisper entry point.

Usage:
    python run.py                              # launch full app (tray + hotkey + UI)
    python run.py --cli --model whisper-turbo  # CLI test: record N seconds and transcribe
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Under pythonw.exe (no console), sys.stdout / sys.stderr are None; any print()
# or warning during import will raise AttributeError and crash the app silently.
# Redirect to log files in %LOCALAPPDATA%\LocalWhisper before importing anything
# that may write on import (torch, pyannote, etc).
if sys.stdout is None or sys.stderr is None:
    _log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LocalWhisper")
    os.makedirs(_log_dir, exist_ok=True)
    sys.stdout = open(os.path.join(_log_dir, "app.log"), "a", encoding="utf-8", buffering=1)
    sys.stderr = open(os.path.join(_log_dir, "app.log.err"), "a", encoding="utf-8", buffering=1)

# Pystray's _win32 backend does `from six.moves import queue`. PySide6's
# shibokensupport installs an import hook (feature_imported) that introspects
# every imported module; on some version combos it ends up calling
# _module_repr_from_spec on a six.moves submodule whose loader is a
# `_SixMetaPathImporter` instance — which has no `_path` attribute. CPython's
# repr code reads `loader._path` and crashes with AttributeError.
# Patch the class to expose `_path = None`, which the repr code accepts.
try:
    import six as _six  # noqa: F401
    if not hasattr(_six._SixMetaPathImporter, "_path"):
        _six._SixMetaPathImporter._path = None
except Exception:
    pass

import numpy as np

from localwhisper.audio import Recorder, SAMPLE_RATE
from localwhisper.transcriber import get_engine, list_models


def cmd_cli(model_key: str, duration: float, device: int | None) -> int:
    print(f"[LocalWhisper CLI] model={model_key}  duration={duration}s  device={device}")
    print("Loading model (first run downloads weights)...")
    t0 = time.time()
    engine = get_engine(model_key)
    engine.load()
    print(f"Model loaded in {time.time() - t0:.1f}s")

    rec = Recorder(device=device)
    print(f"\nRecording {duration:.1f}s — speak now...")
    rec.start()
    t_start = time.time()
    while time.time() - t_start < duration:
        time.sleep(0.05)
    audio = rec.stop()
    print(f"Captured {audio.size / SAMPLE_RATE:.2f}s of audio.")

    t0 = time.time()
    text = engine.transcribe_full(audio, language="pt")
    elapsed = time.time() - t0
    rtf = (audio.size / SAMPLE_RATE) / max(elapsed, 1e-6)
    print(f"\nTranscription ({elapsed:.2f}s, {rtf:.1f}x real-time):")
    print("-" * 60)
    print(text)
    print("-" * 60)
    return 0


def cmd_list_models() -> int:
    for m in list_models():
        print(f"  {m['key']:14s}  {m['display_name']}")
        print(f"  {'':14s}  {m['subtitle']}")
        print(f"  {'':14s}  ~{m['approx_vram_gb']}GB VRAM, ~{m['speed_x_realtime']}x real-time")
        print()
    return 0


def cmd_app() -> int:
    from localwhisper.app import main as app_main

    return app_main()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="localwhisper")
    p.add_argument("--cli", action="store_true", help="Run a one-shot CLI transcription test")
    p.add_argument("--list-models", action="store_true", help="List available models")
    p.add_argument("--model", default="whisper-turbo", choices=list(m["key"] for m in list_models()))
    p.add_argument("--duration", type=float, default=5.0, help="Seconds to record (CLI mode)")
    p.add_argument("--device", type=int, default=None, help="Input device index (sounddevice)")
    args = p.parse_args(argv)

    if args.list_models:
        return cmd_list_models()
    if args.cli:
        return cmd_cli(args.model, args.duration, args.device)
    return cmd_app()


if __name__ == "__main__":
    sys.exit(main())
