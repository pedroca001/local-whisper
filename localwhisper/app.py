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
from .focus import activate_window, get_focus_info
from .hotkey import HotkeyManager
from .injector import (
    ClipboardSnapshot,
    current_clipboard_text,
    paste_clipboard_hotkey,
    release_modifiers,
    replace_selection_with_message,
    restore_clipboard,
    set_clipboard_text_protected,
    snapshot_clipboard,
    type_unicode,
)
from .insertion_policy import input_events_succeeded, target_prefers_clipboard
from .audio_gate import analyze_audio_activity
from .vocabulary import apply_replacements
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
        self._target_hwnd: int = 0
        self._target_focus_hwnd: int = 0
        self._target_app: Optional[str] = None
        self._target_title: Optional[str] = None
        self._t_start: float = 0.0
        self._engine_lock = threading.Lock()
        self._engine_ready = threading.Event()
        self._engine_load_error: Optional[str] = None
        self._engine_thread: Optional[threading.Thread] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_stop = threading.Event()
        self._stream_started = False
        self._session_streaming = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def ensure_engine(self) -> None:
        with self._engine_lock:
            engine_key = f"{self.cfg.model}|{self.cfg.compute_device}|{self.cfg.compute_type}|{self.cfg.models_dir}"
            if self._engine is not None and self._engine_key == engine_key:
                return
            if self._engine is not None:
                try:
                    self._engine.unload()
                except Exception:
                    pass
            logging.info(
                "Loading ASR engine: model=%s language=%s streaming=%s device=%s compute_type=%s",
                self.cfg.model,
                self.cfg.language,
                self.cfg.streaming,
                self.cfg.compute_device,
                self.cfg.compute_type,
            )
            self._engine = get_engine(self.cfg.model, self.cfg.compute_device, self.cfg.compute_type, self.cfg.models_dir)
            self._engine.load()
            self._engine_key = engine_key
            logging.info("ASR engine loaded: %s", getattr(self._engine, "display_name", self.cfg.model))

    def toggle(self) -> None:
        if self._is_recording:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self._is_recording:
            return
        info = get_focus_info()
        self._target_hwnd = int(info.get("hwnd") or 0)
        self._target_focus_hwnd = int(info.get("focus_hwnd") or info.get("caret_hwnd") or 0)
        self._target_app = info.get("process") or None
        self._target_title = info.get("title") or None
        self._injecting = bool(info.get("can_inject"))
        logging.info("Recording target captured: %s", info)

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

        self._stream_stop.clear()
        self._stream_started = False
        self._session_streaming = bool(self.cfg.streaming)
        self._engine_load_error = None
        self._engine_ready.clear()
        self._engine_thread = threading.Thread(
            target=self._load_engine_for_recording,
            name="EngineLoadThread",
            daemon=True,
        )
        self._engine_thread.start()

    def _load_engine_for_recording(self) -> None:
        """Load the model off the UI thread, then start live streaming if still recording."""
        try:
            self.ensure_engine()
            if (
                self._session_streaming
                and not self._stream_stop.is_set()
                and self._is_recording
                and self._recorder is not None
                and self._recorder.running
            ):
                self._engine.start_stream(
                    language=self.cfg.language,
                    on_delta=self._emit_delta,
                    vad_filter=self.cfg.silence_removal,
                    vocabulary=self.cfg.vocabulary,
                )
                self._stream_started = True
                self._stream_thread = threading.Thread(target=self._stream_loop, name="StreamThread", daemon=True)
                self._stream_thread.start()
        except Exception as e:
            self._engine_load_error = str(e)
            logging.exception("Failed to load or start the speech model")
            if self._is_recording:
                self._stream_stop.set()
                if self._recorder:
                    try:
                        self._recorder.stop()
                    except Exception:
                        pass
                    self._recorder = None
                self._is_recording = False
                self.stopped.emit()
            self.error_occurred.emit("Could not load the speech model", str(e))
        finally:
            self._engine_ready.set()

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

        # Re-check focus right before finalizing. Detection at start can miss
        # apps where UIA is slow to populate (Electron, freshly-focused fields).
        # If the user is still on the same hwnd OR a different injectable one,
        # update the target so injection actually happens.
        try:
            current = get_focus_info()
            same_target = bool(current.get("hwnd")) and int(current.get("hwnd") or 0) == self._target_hwnd
            if current.get("can_inject") or (same_target and not self._injecting):
                if current.get("hwnd"):
                    self._target_hwnd = int(current.get("hwnd") or self._target_hwnd)
                    self._target_focus_hwnd = int(current.get("focus_hwnd") or current.get("caret_hwnd") or self._target_focus_hwnd)
                    self._target_app = current.get("process") or self._target_app
                    self._target_title = current.get("title") or self._target_title
                self._injecting = True
                logging.info(
                    "Stop: re-checked focus, can_inject=True target=%s hwnd=%s",
                    self._target_app,
                    self._target_hwnd,
                )
            else:
                logging.info(
                    "Stop: re-checked focus, can_inject=%s target=%s",
                    self._injecting,
                    current.get("process"),
                )
        except Exception:
            logging.exception("Stop: focus re-check failed")

        duration_ms = int((time.time() - self._t_start) * 1000)

        # Background finalize so UI doesn't block
        threading.Thread(
            target=self._finalize_in_background,
            args=(audio, duration_ms),
            daemon=True,
        ).start()

    def _finalize_in_background(self, audio: np.ndarray, duration_ms: int) -> None:
        activity = analyze_audio_activity(audio)
        if not activity.has_voice:
            logging.info(
                "Skipping transcription for silent audio: duration=%.2fs rms=%.5f peak=%.5f voiced_ratio=%.4f",
                activity.duration_s,
                activity.rms,
                activity.peak,
                activity.voiced_ratio,
            )
            self.finalized.emit("", duration_ms)
            return

        try:
            self._wait_for_engine_ready()
            if self._session_streaming:
                self._join_stream_thread()
                if self._stream_started:
                    final_text = self._engine.finalize_stream()
                else:
                    final_text = self._engine.transcribe_full(
                        audio,
                        language=self.cfg.language,
                        vad_filter=self.cfg.silence_removal,
                        vocabulary=self.cfg.vocabulary,
                    )
            else:
                final_text = self._engine.transcribe_full(
                    audio,
                    language=self.cfg.language,
                    vad_filter=self.cfg.silence_removal,
                    vocabulary=self.cfg.vocabulary,
                )
        except Exception as e:
            logging.exception("Transcription failed")
            self.error_occurred.emit("Transcription failed", str(e))
            final_text = ""

        text = apply_replacements(
            (final_text or "").strip(),
            self.cfg.vocabulary_replacements,
            self.cfg.vocabulary,
        ).strip()
        self.finalized.emit(text, duration_ms)

    def can_inject_now(self) -> bool:
        return self._injecting

    def _wait_for_engine_ready(self) -> None:
        if not self._engine_ready.wait(timeout=120.0):
            raise RuntimeError("Speech model did not finish loading in time.")
        if self._engine_load_error:
            raise RuntimeError(self._engine_load_error)
        if self._engine is None:
            raise RuntimeError("Speech model is not available.")

    def _join_stream_thread(self) -> None:
        thread = self._stream_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def invalidate_engine(self) -> None:
        with self._engine_lock:
            self._engine_key = None

    @property
    def target_hwnd(self) -> int:
        return self._target_hwnd

    @property
    def target_focus_hwnd(self) -> int:
        return self._target_focus_hwnd

    @property
    def target_app(self) -> Optional[str]:
        return self._target_app

    @property
    def target_title(self) -> Optional[str]:
        return self._target_title


class App(QObject):
    # Signals used to safely cross from non-Qt threads (pystray, hotkey) into
    # the Qt main thread. Direct method calls or QTimer.singleShot from those
    # threads do not run, because those threads do not own a Qt event loop.
    show_settings_requested = Signal()
    toggle_recording_requested = Signal()
    cancel_recording_requested = Signal()
    copy_last_requested = Signal()
    paste_last_requested = Signal()
    quit_requested = Signal()

    def __init__(self, qapp: QApplication, cfg: Config):
        super().__init__()
        self.qapp = qapp
        self.cfg = cfg
        self._last_text_injected = False
        self._last_entry_text = ""
        self._clipboard_restore_snapshot: ClipboardSnapshot | None = None
        self._clipboard_restore_pending = False
        self._clipboard_restore_generation = 0

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
        self.overlay.update_cancel_hotkey(cfg.hotkey_cancel)
        self.overlay.update_device(cfg.input_device or "Default")

        self.window = SettingsWindow(cfg)
        self.window.hotkey_changed.connect(self._on_hotkey_changed)
        self.window.paste_last_hotkey_changed.connect(self._on_paste_hotkey_changed)
        self.window.config_changed.connect(self._on_config_changed)
        self.window.record_now_requested.connect(self._do_toggle_recording)

        # Cross-thread signals — Qt::QueuedConnection is automatic when sender
        # and receiver live in different threads, which is exactly what we need.
        self.show_settings_requested.connect(self._do_show_settings)
        self.toggle_recording_requested.connect(self._do_toggle_recording)
        self.cancel_recording_requested.connect(self._do_cancel_recording)
        self.copy_last_requested.connect(self._do_copy_last)
        self.paste_last_requested.connect(self._do_paste_last)
        self.quit_requested.connect(self._do_quit)

        self.tray = TrayIcon(
            on_settings=self.show_settings_requested.emit,
            on_record=self.toggle_recording_requested.emit,
            on_copy_last=self.copy_last_requested.emit,
            on_quit=self.quit_requested.emit,
        )
        self.tray.start()

        self.hotkey = HotkeyManager(cfg.hotkey_toggle, self.toggle_recording_requested.emit)
        if not self.hotkey.start():
            QTimer.singleShot(500, self._warn_hotkey)
        self.cancel_hotkey: Optional[HotkeyManager] = None

        # Hotkey to paste the last transcription into the focused window.
        self.paste_hotkey = HotkeyManager(cfg.hotkey_paste_last, self.paste_last_requested.emit)
        if not self.paste_hotkey.start():
            logging.warning(
                "Could not register paste-last hotkey %r: %s",
                cfg.hotkey_paste_last,
                self.paste_hotkey.error,
            )

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

    def _on_paste_hotkey_changed(self, combo: str) -> None:
        if not self.paste_hotkey.change(combo):
            msg = QMessageBox(
                QMessageBox.Icon.Warning, "Hotkey conflict",
                f"Could not register paste hotkey '{combo}'.\n\n"
                f"{self.paste_hotkey.error or 'It is likely already in use by another application.'}\n\n"
                "Open Configuration to choose a different combination.")
            msg.exec()

    def _on_config_changed(self) -> None:
        self.overlay.update_device(self.cfg.input_device or "Default")
        self.overlay.update_cancel_hotkey(self.cfg.hotkey_cancel)
        self.controller.invalidate_engine()
        sounds.set_output_device(self.cfg.output_device)
        sounds.set_volume(self.cfg.sound_volume)

    # ---- Slots that run on the Qt main thread ----
    def _do_toggle_recording(self) -> None:
        self.controller.toggle()

    def _do_cancel_recording(self) -> None:
        self.controller.cancel()

    def _do_copy_last(self) -> None:
        if self._last_entry_text:
            QApplication.clipboard().setText(self._last_entry_text)

    def _do_paste_last(self) -> None:
        """Paste the last transcription into whatever window currently has focus."""
        text = self._last_entry_text
        if not text:
            return
        info = get_focus_info()
        self._inject_text_into(
            text,
            int(info.get("hwnd") or 0),
            int(info.get("focus_hwnd") or info.get("caret_hwnd") or 0),
            info.get("process") or None,
            info.get("title") or None,
        )

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
            self.paste_hotkey.stop()
        except Exception:
            pass
        try:
            self._stop_cancel_hotkey()
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
        self._last_text_injected = False
        self.tray.set_state("recording")
        self._start_cancel_hotkey()
        # Always show the overlay so the user has visual confirmation that
        # recording started — even when text is being injected somewhere.
        self.overlay.show_at_top_center()

    def _on_stopped(self) -> None:
        self._stop_cancel_hotkey()
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
                self._inject_text(delta)
            except Exception as e:
                self._last_text_injected = False
                logging.exception("Text injection failed")
                self._on_error("Text injection failed", str(e))
        else:
            self._last_text_injected = False
            logging.info("No injectable target was captured; will show overlay on finalize")

    def _inject_text(self, text: str) -> bool:
        return self._inject_text_into(
            text,
            self.controller.target_hwnd,
            self.controller.target_focus_hwnd,
            self.controller.target_app,
            self.controller.target_title,
        )

    def _inject_text_into(
        self,
        text: str,
        target_hwnd: int,
        target_focus_hwnd: int,
        target_app: Optional[str],
        target_title: Optional[str],
    ) -> bool:
        if not text:
            return False
        activate_window(target_hwnd, target_focus_hwnd)
        release_modifiers()
        time.sleep(0.02)

        method = "win32_message"
        sent = len(text)
        injected = replace_selection_with_message(target_focus_hwnd, text)

        prefers_clipboard = self._target_prefers_clipboard(target_app, target_title)
        if not injected and not prefers_clipboard:
            method = "unicode"
            sent = type_unicode(text)
            injected = input_events_succeeded(sent, via_clipboard=False)
        if not injected:
            method = "clipboard"
            sent = self._paste_via_clipboard(text, target_hwnd, target_focus_hwnd)
            injected = input_events_succeeded(sent, via_clipboard=True)
        if not injected and prefers_clipboard:
            method = "unicode"
            sent = type_unicode(text)
            injected = input_events_succeeded(sent, via_clipboard=False)

        self._last_text_injected = self._last_text_injected or injected
        logging.info(
            "Text injection attempted: chars=%s hwnd=%s focus_hwnd=%s app=%s method=%s sent=%s success=%s",
            len(text),
            target_hwnd,
            target_focus_hwnd,
            target_app,
            method,
            sent,
            injected,
        )
        return injected

    def _target_prefers_clipboard(self, app: Optional[str] = None, title: Optional[str] = None) -> bool:
        return target_prefers_clipboard(
            self.controller.target_app if app is None else app,
            self.controller.target_title if title is None else title,
        )

    def _paste_via_clipboard(self, text: str, target_hwnd: int, target_focus_hwnd: int) -> int:
        if not self._clipboard_restore_pending:
            self._clipboard_restore_snapshot = snapshot_clipboard()
            self._clipboard_restore_pending = self._clipboard_restore_snapshot is not None

        set_clipboard_text_protected(text)
        activate_window(target_hwnd, target_focus_hwnd)
        release_modifiers()
        time.sleep(0.06)
        sent = paste_clipboard_hotkey()

        def restore_later() -> None:
            try:
                if generation != self._clipboard_restore_generation:
                    return
                if self._clipboard_restore_snapshot is not None and current_clipboard_text() == text:
                    restore_clipboard_snapshot = self._clipboard_restore_snapshot
                    restore_clipboard(restore_clipboard_snapshot)
            except Exception:
                pass
            finally:
                if generation == self._clipboard_restore_generation:
                    self._clipboard_restore_snapshot = None
                    self._clipboard_restore_pending = False

        self._clipboard_restore_generation += 1
        generation = self._clipboard_restore_generation
        QTimer.singleShot(900, restore_later)
        return sent

    def _on_finalized(self, text: str, duration_ms: int) -> None:
        logging.info("Finalized transcription: duration_ms=%s chars=%s", duration_ms, len(text or ""))
        if text and self.controller.can_inject_now() and not self._last_text_injected:
            try:
                self._inject_text(text)
            except Exception as e:
                self._last_text_injected = False
                logging.exception("Final text injection failed")
                self._on_error("Text injection failed", str(e))
        if text:
            self._last_entry_text = text
            try:
                storage.add_transcription(
                    text=text,
                    duration_ms=duration_ms,
                    model=self.cfg.model,
                    target_app=self.controller.target_app,
                    target_window_title=self.controller.target_title,
                    injected=self._last_text_injected,
                    save_dir=self.cfg.save_dir,
                )
            except Exception:
                logging.exception("Save failed")
        # Only show overlay if injection failed or was never attempted.
        # Injection success is tracked across all deltas in self._last_text_injected.
        if text and not self._last_text_injected:
            self.overlay.show_result_text(text)
        # Brief "complete" flash on the tray (auto-resets to ready)
        self.tray.flash_complete()
        try:
            self.window.page_history.refresh_async()
        except Exception:
            pass

    def _start_cancel_hotkey(self) -> None:
        self._stop_cancel_hotkey()
        self.cancel_hotkey = HotkeyManager(self.cfg.hotkey_cancel, self.cancel_recording_requested.emit)
        if not self.cancel_hotkey.start():
            logging.warning("Could not register cancel hotkey %r: %s", self.cfg.hotkey_cancel, self.cancel_hotkey.error)

    def _stop_cancel_hotkey(self) -> None:
        if self.cancel_hotkey is not None:
            try:
                self.cancel_hotkey.stop()
            finally:
                self.cancel_hotkey = None

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
