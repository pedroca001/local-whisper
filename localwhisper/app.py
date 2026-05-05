"""LocalWhisper bootstrap: tray + Qt event loop + hotkey + recording pipeline."""
from __future__ import annotations

import sys
import threading
import time
import logging
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from . import diagnostics, sounds, storage
from .audio import Recorder, list_input_devices
from .config import Config
from .focus import can_inject_text, get_focus_info
from .hotkey import HotkeyManager
from .injector import type_unicode
from .assets import app_icon_paths
from .transcriber import get_engine
from .tray import TrayIcon
from .ui.overlay_recording import RecordingOverlay
from .ui.settings_window import SettingsWindow


class RecordingController(QObject):
    """Owns the recording state machine. Lives on the Qt main thread."""

    delta_ready = Signal(str)
    finalized = Signal(str, int)  # text, duration_ms
    started = Signal()
    stopped = Signal()
    audio_level = Signal(float)
    error_occurred = Signal(str, str)  # title, detail

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._engine = None
        self._engine_key: Optional[str] = None
        self._recorder: Optional[Recorder] = None
        self._is_recording = False
        self._injecting = False
        self._target_app: Optional[str] = None
        self._target_title: Optional[str] = None
        self._t_start: float = 0.0
        self._lock = threading.Lock()
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_stop = threading.Event()

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def ensure_engine(self) -> None:
        if self._engine is not None and self._engine_key == self.cfg.model:
            return
        if self._engine is not None:
            try:
                self._engine.unload()
            except Exception:
                pass
        logging.info("Loading ASR engine: model=%s language=%s streaming=%s", self.cfg.model, self.cfg.language, self.cfg.streaming)
        self._engine = get_engine(self.cfg.model)
        self._engine.load()
        self._engine_key = self.cfg.model
        logging.info("ASR engine loaded: %s", getattr(self._engine, "display_name", self.cfg.model))

    def toggle(self) -> None:
        if self._is_recording:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self._is_recording:
            return
        try:
            self.ensure_engine()
        except Exception as e:
            logging.exception("Failed to load model")
            self.error_occurred.emit("Could not load the speech model", str(e))
            return

        info = get_focus_info()
        self._target_app = info.get("process") or None
        self._target_title = info.get("title") or None
        self._injecting = bool(info.get("can_inject"))

        device_idx = self._resolve_device()
        self._recorder = Recorder(device=device_idx, on_block=self._on_audio_block)
        try:
            self._recorder.start()
        except Exception as e:
            logging.exception("Recorder start failed")
            self.error_occurred.emit("Could not start microphone recording", str(e))
            return
        self._t_start = time.time()
        self._is_recording = True
        self.started.emit()

        # Start streaming thread if streaming mode
        self._stream_stop.clear()
        if self.cfg.streaming:
            self._engine.start_stream(language=self.cfg.language, on_delta=self._emit_delta)
            self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self._stream_thread.start()

    def _resolve_device(self) -> Optional[int]:
        if not self.cfg.input_device:
            return None
        for d in list_input_devices():
            if d["name"] == self.cfg.input_device:
                return d["index"]
        return None

    def _on_audio_block(self, samples: np.ndarray) -> None:
        # Compute RMS level for waveform animation
        try:
            rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
            level = min(1.0, rms * 6.0)
            self.audio_level.emit(level)
        except Exception:
            pass

    def _stream_loop(self) -> None:
        if not self._recorder:
            return
        accum: list[np.ndarray] = []
        last_push = time.time()
        while not self._stream_stop.is_set() and self._recorder and self._recorder.running:
            chunk = self._recorder.get_chunk(timeout=0.1)
            if chunk is not None:
                accum.append(chunk)
            now = time.time()
            if accum and now - last_push >= 0.6:
                audio = np.concatenate(accum)
                accum = []
                last_push = now
                try:
                    self._engine.push_chunk(audio)
                except Exception as e:
                    logging.exception("Streaming push_chunk failed")

    def _emit_delta(self, delta: str) -> None:
        if not delta:
            return
        self.delta_ready.emit(delta)

    def cancel(self) -> None:
        if not self._is_recording:
            return
        self._stream_stop.set()
        if self._recorder:
            self._recorder.stop()
            self._recorder = None
        self._is_recording = False
        self.stopped.emit()

    def stop(self) -> None:
        if not self._is_recording:
            return
        self._stream_stop.set()
        audio = np.zeros(0, dtype=np.float32)
        if self._recorder:
            audio = self._recorder.stop()
            self._recorder = None
        self._is_recording = False
        self.stopped.emit()

        duration_ms = int((time.time() - self._t_start) * 1000)

        # Background finalize so UI doesn't block
        threading.Thread(
            target=self._finalize_in_background,
            args=(audio, duration_ms),
            daemon=True,
        ).start()

    def _finalize_in_background(self, audio: np.ndarray, duration_ms: int) -> None:
        try:
            if self.cfg.streaming:
                final_text = self._engine.finalize_stream()
            else:
                final_text = self._engine.transcribe_full(audio, language=self.cfg.language)
        except Exception as e:
            logging.exception("Transcription failed")
            self.error_occurred.emit("Transcription failed", str(e))
            final_text = ""

        text = (final_text or "").strip()
        # In final-dump mode (or when streaming yielded nothing), emit the text now.
        if not self.cfg.streaming and text:
            self.delta_ready.emit(text)

        # Save to history
        try:
            storage.add_transcription(
                text=text,
                duration_ms=duration_ms,
                model=self.cfg.model,
                target_app=self._target_app,
                target_window_title=self._target_title,
                injected=self._injecting,
                save_dir=self.cfg.save_dir,
            )
        except Exception as e:
            logging.exception("Save failed")

        self.finalized.emit(text, duration_ms)

    def can_inject_now(self) -> bool:
        return self._injecting


class App(QObject):
    # Signals used to safely cross from non-Qt threads (pystray, hotkey) into
    # the Qt main thread. Direct method calls or QTimer.singleShot from those
    # threads do not run, because those threads do not own a Qt event loop.
    show_settings_requested = Signal()
    toggle_recording_requested = Signal()
    quit_requested = Signal()

    def __init__(self, qapp: QApplication, cfg: Config):
        super().__init__()
        self.qapp = qapp
        self.cfg = cfg

        self.controller = RecordingController(cfg)
        self.controller.delta_ready.connect(self._on_delta)
        self.controller.started.connect(self._on_started)
        self.controller.stopped.connect(self._on_stopped)
        self.controller.audio_level.connect(self._on_level)
        self.controller.finalized.connect(self._on_finalized)
        self.controller.error_occurred.connect(self._on_error)

        sounds.set_output_device(cfg.output_device)
        sounds.set_volume(cfg.sound_volume)

        self.overlay = RecordingOverlay()
        self.overlay.update_hotkey(cfg.hotkey_toggle)
        self.overlay.update_device(cfg.input_device or "Default")

        self.window = SettingsWindow(cfg)
        self.window.hotkey_changed.connect(self._on_hotkey_changed)
        self.window.config_changed.connect(self._on_config_changed)
        self.window.record_now_requested.connect(self._do_toggle_recording)

        # Cross-thread signals — Qt::QueuedConnection is automatic when sender
        # and receiver live in different threads, which is exactly what we need.
        self.show_settings_requested.connect(self._do_show_settings)
        self.toggle_recording_requested.connect(self._do_toggle_recording)
        self.quit_requested.connect(self._do_quit)

        self.tray = TrayIcon(
            on_settings=self.show_settings_requested.emit,
            on_record=self.toggle_recording_requested.emit,
            on_quit=self.quit_requested.emit,
        )
        self.tray.start()

        self.hotkey = HotkeyManager(cfg.hotkey_toggle, self.toggle_recording_requested.emit)
        if not self.hotkey.start():
            QTimer.singleShot(500, self._warn_hotkey)

    def _warn_hotkey(self):
        msg = QMessageBox(QMessageBox.Icon.Warning, "Hotkey conflict",
                          f"Could not register hotkey '{self.cfg.hotkey_toggle}'.\n\n"
                          f"{self.hotkey.error or 'It is likely already in use by another application.'}\n\n"
                          "Open Configuration to choose a different combination.")
        msg.exec()
        self._do_show_settings()

    def _on_hotkey_changed(self, combo: str) -> None:
        if not self.hotkey.change(combo):
            self._warn_hotkey()
        else:
            self.overlay.update_hotkey(combo)

    def _on_config_changed(self) -> None:
        self.overlay.update_device(self.cfg.input_device or "Default")
        self.controller._engine_key = None  # force engine reload on next start
        sounds.set_output_device(self.cfg.output_device)
        sounds.set_volume(self.cfg.sound_volume)

    # ---- Slots that run on the Qt main thread ----
    def _do_toggle_recording(self) -> None:
        self.controller.toggle()

    def _do_show_settings(self) -> None:
        self.window.show()
        self.window.setWindowState(self.window.windowState() & ~Qt.WindowMinimized)
        self.window.raise_()
        self.window.activateWindow()

    def _do_quit(self) -> None:
        try:
            self.hotkey.stop()
        except Exception:
            pass
        try:
            self.tray.stop()
        except Exception:
            pass
        self.qapp.quit()

    # ---- Recording lifecycle ----
    def _on_started(self) -> None:
        if self.cfg.sound_effects:
            sounds.play_start()
        self.tray.set_state("recording")
        # Always show the overlay so the user has visual confirmation that
        # recording started — even when text is being injected somewhere.
        self.overlay.show_at_top_center()

    def _on_stopped(self) -> None:
        if self.cfg.sound_effects:
            sounds.play_stop()
        # Audio capture stopped — model is now finalizing the transcription.
        self.tray.set_state("processing")
        self.overlay.fade_out_and_hide()

    def _on_level(self, level: float) -> None:
        self.overlay.set_audio_level(level)

    def _on_delta(self, delta: str) -> None:
        if self.controller.can_inject_now():
            try:
                type_unicode(delta)
            except Exception as e:
                logging.exception("Text injection failed")
                self._on_error("Text injection failed", str(e))

    def _on_finalized(self, text: str, duration_ms: int) -> None:
        logging.info("Finalized transcription: duration_ms=%s chars=%s", duration_ms, len(text or ""))
        # Brief "complete" flash on the tray (auto-resets to ready)
        self.tray.flash_complete()
        try:
            self.window.page_history.refresh_async()
        except Exception:
            pass

    def _on_error(self, title: str, detail: str) -> None:
        logging.error("%s: %s", title, detail)
        msg = QMessageBox(
            QMessageBox.Icon.Warning,
            title,
            f"{detail}\n\nA diagnostic log was written to:\n{diagnostics.LOG_PATH}",
        )
        msg.exec()


def main() -> int:
    log_path = diagnostics.setup_logging()
    logging.info("LocalWhisper starting; executable=%s; frozen=%s; log=%s", sys.executable, getattr(sys, "frozen", False), log_path)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.localwhisper.app")
        except Exception:
            pass

    # GPU detection must happen before ctranslate2 is ever imported so that
    # os.add_dll_directory() registers the CUDA bin path in time.
    from . import gpu as _gpu
    _gpu.setup()

    cfg = Config.load()
    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("LocalWhisper")

    # App icon used by Qt for window title bar, alt-tab and taskbar.
    from PySide6.QtGui import QIcon, QImageReader

    qicon = QIcon()
    for path in app_icon_paths():
        size = QImageReader(str(path)).size()
        if size.isValid():
            qicon.addFile(str(path), size)
        else:
            qicon.addFile(str(path))
    if not qicon.isNull():
        qapp.setWindowIcon(qicon)

    app = App(qapp, cfg)
    if not qicon.isNull():
        app.window.setWindowIcon(qicon)

    # On first launch, show window so the user sees something happen
    app.window.show()

    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
