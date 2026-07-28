"""UI page: pick an audio/video file, transcribe it (optionally with speaker diarization).

The heavy work runs on a QThread so the UI stays responsive. Progress and the
final transcript come back via Qt signals.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import Config
from ...transcriber.file_transcriber import CancellationToken, FileTranscriptionCancelled
from ..widgets.card import Card

SUPPORTED_FILTER = (
    "Audio/Video files ("
    "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma "
    "*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.3gp *.wmv"
    ");;All files (*)"
)


# ─── worker thread ─────────────────────────────────────────────────────────
class _Worker(QObject):
    progress = Signal(str, float)              # stage label, 0..1 (-1 = indeterminate)
    finished_ok = Signal(object)               # FileTranscript
    failed = Signal(str)                       # error message
    cancelled = Signal()

    def __init__(
        self,
        paths: list[str],
        model_key: str,
        language: str,
        diarize: bool,
        hf_token: str,
        min_speakers: Optional[int],
        max_speakers: Optional[int],
        models_dir: str,
        compute_device: str,
        compute_type: str,
    ):
        super().__init__()
        self.paths = paths
        self.model_key = model_key
        self.language = language
        self.diarize = diarize
        self.hf_token = hf_token
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.models_dir = models_dir
        self.compute_device = compute_device
        self.compute_type = compute_type
        self.cancel_token = CancellationToken()

    def cancel(self) -> None:
        self.cancel_token.cancel()

    def run(self) -> None:
        engine = None
        try:
            # Lazy imports keep app startup fast — these pull in faster-whisper, ffmpeg, etc.
            from ...transcriber import get_engine
            from ...transcriber.file_transcriber import transcribe_file

            self.progress.emit("Loading speech model…", 0.02)
            engine = get_engine(
                self.model_key,
                self.compute_device,
                self.compute_type,
                self.models_dir,
            )
            engine.load()

            results = []
            failures = []
            total = len(self.paths)
            for index, path in enumerate(self.paths, 1):
                self.cancel_token.raise_if_cancelled()
                prefix = f"[{index}/{total}] {Path(path).name}"
                try:
                    result = transcribe_file(
                        path,
                        engine=engine,
                        language=self.language,
                        diarize=self.diarize,
                        hf_token=self.hf_token or None,
                        min_speakers=self.min_speakers,
                        max_speakers=self.max_speakers,
                        on_progress=lambda label, pct, p=prefix: self.progress.emit(
                            f"{p} — {label}",
                            pct,
                        ),
                        cancel_token=self.cancel_token,
                    )
                    results.append((path, result))
                except FileTranscriptionCancelled:
                    raise
                except Exception as exc:
                    logging.exception("Batch item failed: %s", path)
                    failures.append((path, str(exc)))
                    self.progress.emit(f"{prefix} — failed; continuing", 0.0)
            if not results and failures:
                detail = "\n".join(f"{Path(path).name}: {error}" for path, error in failures)
                self.failed.emit(detail)
            else:
                self.finished_ok.emit({"results": results, "failures": failures})
        except FileTranscriptionCancelled:
            self.cancelled.emit()
        except Exception as exc:
            logging.exception("File transcription failed")
            self.failed.emit(str(exc))
        finally:
            if engine is not None:
                try:
                    engine.unload()
                except Exception:
                    logging.exception("Could not unload file transcription engine")


# ─── page ──────────────────────────────────────────────────────────────────
class TranscribeFilePage(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._result = None  # FileTranscript
        self._results: list[tuple[str, object]] = []
        self._paths: list[str] = []
        self.setAcceptDrops(True)

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(10)

        title = QLabel("Transcribe File")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)

        sub = QLabel(
            "Add one or many audio/video files, choose the language, "
            "and (optionally) identify who is speaking."
        )
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        sub.setWordWrap(True)
        v.addWidget(sub)

        # ── File picker ────────────────────────────────────────────────
        card1 = Card()
        card1.add_title("1. Source")
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("No files selected")
        self.path_edit.setReadOnly(True)
        self.path_edit.setMinimumWidth(260)
        browse = QPushButton("Add files…")
        browse.clicked.connect(self._pick_file)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(self.path_edit)
        wl.addWidget(browse)
        card1.add_row(
            "Audio/Video files",
            wrap,
            sub="Build a queue. The speech model stays loaded between files for faster batch processing.",
        )
        self.file_queue = QListWidget()
        self.file_queue.setMinimumHeight(90)
        self.file_queue.setMaximumHeight(150)
        card1.add_widget(self.file_queue)
        queue_actions = QWidget()
        queue_layout = QHBoxLayout(queue_actions)
        queue_layout.setContentsMargins(18, 0, 18, 12)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_selected_file)
        clear = QPushButton("Clear queue")
        clear.clicked.connect(self._clear_files)
        queue_layout.addWidget(remove)
        queue_layout.addWidget(clear)
        queue_layout.addStretch(1)
        card1.add_widget(queue_actions)
        v.addWidget(card1)

        # ── Options ────────────────────────────────────────────────────
        card2 = Card()
        card2.add_title("2. Options")

        # Language
        self._lang_codes = {
            "Auto-detect": "auto",
            "Portuguese (Brazil)": "pt-BR",
            "Portuguese (Portugal)": "pt-PT",
            "English": "en",
            "Spanish": "es",
            "French": "fr",
            "German": "de",
            "Italian": "it",
            "Japanese": "ja",
            "Chinese": "zh",
            "Russian": "ru",
            "Dutch": "nl",
            "Polish": "pl",
            "Korean": "ko",
            "Arabic": "ar",
        }
        self.language = QComboBox()
        self.language.addItems(list(self._lang_codes.keys()))
        # Default to current global language if it's in the map; else auto
        wanted = cfg.language if cfg.language in self._lang_codes.values() else "auto"
        for label, code in self._lang_codes.items():
            if code == wanted:
                self.language.setCurrentText(label)
                break
        card2.add_row(
            "Language",
            self.language,
            sub="Pick 'Auto-detect' to let the model figure it out (slightly slower).",
        )

        # Diarization toggle
        self.diarize_box = QCheckBox("Identify speakers (diarization)")
        self.diarize_box.setChecked(bool(cfg.file_diarize))
        self.diarize_box.toggled.connect(self._on_diarize_toggled)
        card2.add_row(
            "Speakers",
            self.diarize_box,
            sub="Groups segments by voice and labels them as Speaker 1, Speaker 2, …. "
                "Requires a free HuggingFace token (see Configuration page).",
        )

        # Min / max speakers
        self.min_spk = QSpinBox()
        self.min_spk.setRange(0, 20)
        self.min_spk.setValue(0)
        self.min_spk.setSpecialValueText("auto")
        self.max_spk = QSpinBox()
        self.max_spk.setRange(0, 20)
        self.max_spk.setValue(0)
        self.max_spk.setSpecialValueText("auto")
        spk_wrap = QWidget()
        sw = QHBoxLayout(spk_wrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.addWidget(QLabel("min"))
        sw.addWidget(self.min_spk)
        sw.addSpacing(8)
        sw.addWidget(QLabel("max"))
        sw.addWidget(self.max_spk)
        sw.addStretch(1)
        card2.add_row(
            "Speaker count",
            spk_wrap,
            sub="Leave both at 'auto' to detect automatically. Set if you already know how many people speak.",
        )

        v.addWidget(card2)

        # ── Run + progress ─────────────────────────────────────────────
        card3 = Card()
        card3.add_title("3. Run")
        self.run_btn = QPushButton("Transcribe")
        self.run_btn.setObjectName("PrimaryButton")
        self.run_btn.clicked.connect(self._start)
        self.run_btn.setEnabled(False)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)

        run_row = QWidget()
        rr = QHBoxLayout(run_row)
        rr.setContentsMargins(0, 0, 16, 0)
        rr.addStretch(1)
        rr.addWidget(self.cancel_btn)
        rr.addWidget(self.run_btn)
        card3.add_widget(run_row)

        self.status_lbl = QLabel("Pick a file to get started.")
        self.status_lbl.setStyleSheet("color: #3a3a3c; background: #f5f5f7; border-radius: 6px; padding: 8px 10px;")
        self.status_lbl.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        prog_wrap = QWidget()
        pwl = QVBoxLayout(prog_wrap)
        pwl.setContentsMargins(18, 0, 18, 14)
        pwl.setSpacing(6)
        pwl.addWidget(self.status_lbl)
        pwl.addWidget(self.progress)
        card3.add_widget(prog_wrap)

        v.addWidget(card3)

        # ── Result ─────────────────────────────────────────────────────
        card4 = Card()
        card4.add_title("4. Transcript")

        self.result_view = QTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setMinimumHeight(260)
        self.result_view.setPlaceholderText("Your transcript will appear here.")
        self.result_view.setStyleSheet(
            "QTextEdit { background: #ffffff; color: #111113; border: 1px solid #d2d2d7;"
            "border-radius: 8px; padding: 10px; selection-background-color: #007aff;"
            "selection-color: #ffffff; }"
        )
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self.result_view.setFont(mono)

        actions_wrap = QWidget()
        aw = QHBoxLayout(actions_wrap)
        aw.setContentsMargins(0, 0, 0, 0)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.setEnabled(False)
        self.save_btn = QPushButton("Save .txt…")
        self.save_btn.clicked.connect(self._save_txt)
        self.save_btn.setEnabled(False)
        self.save_format = QComboBox()
        self.save_format.addItems(["TXT", "SRT", "VTT", "JSON"])
        self.save_format.setEnabled(False)
        self.timestamps_box = QCheckBox("Show timestamps")
        self.timestamps_box.toggled.connect(self._refresh_view)
        aw.addWidget(self.timestamps_box)
        aw.addStretch(1)
        aw.addWidget(self.copy_btn)
        aw.addWidget(self.save_format)
        aw.addWidget(self.save_btn)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 6, 18, 14)
        bl.setSpacing(8)
        bl.addWidget(self.result_view)
        bl.addWidget(actions_wrap)
        card4.add_widget(body)

        v.addWidget(card4, stretch=1)

    # ── helpers ───────────────────────────────────────────────────────
    def _on_diarize_toggled(self, on: bool) -> None:
        self.cfg.file_diarize = on
        self.cfg.save()

    def _pick_file(self) -> None:
        start_dir = self.cfg.file_last_dir or str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select audio or video files",
            start_dir,
            SUPPORTED_FILTER,
        )
        if not paths:
            return
        self._add_files(paths)
        self.cfg.file_last_dir = str(Path(paths[0]).parent)
        self.cfg.save()

    def _add_files(self, paths: list[str]) -> None:
        known = {str(Path(path).resolve()).casefold() for path in self._paths}
        for candidate in paths:
            path = str(Path(candidate).resolve())
            if Path(path).is_file() and path.casefold() not in known:
                self._paths.append(path)
                known.add(path.casefold())
        self._refresh_queue()

    def _remove_selected_file(self) -> None:
        row = self.file_queue.currentRow()
        if 0 <= row < len(self._paths):
            self._paths.pop(row)
        self._refresh_queue()

    def _clear_files(self) -> None:
        self._paths.clear()
        self._refresh_queue()

    def _refresh_queue(self) -> None:
        self.file_queue.clear()
        self.file_queue.addItems([Path(path).name for path in self._paths])
        count = len(self._paths)
        if count == 0:
            self.path_edit.clear()
            self.status_lbl.setText("Add files or drop them here to get started.")
        elif count == 1:
            self.path_edit.setText(self._paths[0])
            self.status_lbl.setText(f"Ready: {Path(self._paths[0]).name}")
        else:
            self.path_edit.setText(f"{count} files queued")
            self.status_lbl.setText(f"Ready to transcribe {count} files.")
        self.run_btn.setEnabled(count > 0 and self._thread is None)

    def _selected_lang(self) -> str:
        return self._lang_codes.get(self.language.currentText(), "auto")

    # ── execution ─────────────────────────────────────────────────────
    def _start(self) -> None:
        if not self._paths:
            return

        diarize = self.diarize_box.isChecked()
        if diarize and not (self.cfg.hf_token or os.environ.get("HF_TOKEN")):
            res = QMessageBox.question(
                self,
                "HuggingFace token missing",
                "Speaker diarization needs a free HuggingFace access token.\n\n"
                "1) Accept the model terms at\n"
                "    https://huggingface.co/pyannote/speaker-diarization-3.1\n"
                "2) Generate a token at\n"
                "    https://huggingface.co/settings/tokens\n"
                "3) Paste it in Configuration → HuggingFace token.\n\n"
                "Continue without speaker labels?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if res != QMessageBox.StandardButton.Yes:
                return
            diarize = False

        # Lock UI
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.copy_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.save_format.setEnabled(False)
        self.result_view.clear()
        self.progress.setValue(0)
        self.status_lbl.setText("Starting…")

        min_spk = self.min_spk.value() or None
        max_spk = self.max_spk.value() or None

        self._thread = QThread(self)
        self._worker = _Worker(
            paths=list(self._paths),
            model_key=self.cfg.model,
            language=self._selected_lang(),
            diarize=diarize,
            hf_token=self.cfg.hf_token,
            min_speakers=min_spk,
            max_speakers=max_spk,
            models_dir=self.cfg.models_dir,
            compute_device=self.cfg.compute_device,
            compute_type=self.cfg.compute_type,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText("Cancellation requested — waiting for current step to finish…")
        if self._worker is not None:
            self._worker.cancel()

    def _on_progress(self, label: str, pct: float) -> None:
        self.status_lbl.setText(label)
        if pct < 0:
            self.progress.setRange(0, 0)
        else:
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 1000)
            self.progress.setValue(int(max(0.0, min(1.0, pct)) * 1000))

    def _on_finished_ok(self, payload: dict) -> None:
        results = list(payload.get("results") or [])
        failures = list(payload.get("failures") or [])
        self._results = results
        self._result = results[0][1] if results else None
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        duration = sum(result.duration_s for _path, result in results)
        segments = sum(len(result.segments) for _path, result in results)
        msg = f"Done — {len(results)} file(s), {duration:.1f}s of audio, {segments} segment(s)"
        if failures:
            msg += f"; {len(failures)} failed"
        self.status_lbl.setText(msg)
        self._refresh_view()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.copy_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.save_format.setEnabled(True)

    def _on_failed(self, err: str) -> None:
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.status_lbl.setText(f"Failed: {err}")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QMessageBox.warning(self, "Transcription failed", err)

    def _on_cancelled(self) -> None:
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.status_lbl.setText("Cancelled. No partial output was saved.")
        self.run_btn.setEnabled(bool(self._paths))
        self.cancel_btn.setEnabled(False)

    def _cleanup_thread(self) -> None:
        if self._thread is not None:
            self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None

    # ── output rendering ──────────────────────────────────────────────
    def _refresh_view(self) -> None:
        if not self._results:
            return
        chunks = []
        for path, result in self._results:
            text = result.to_txt(with_timestamps=self.timestamps_box.isChecked())
            if len(self._results) > 1:
                chunks.append(f"=== {Path(path).name} ===\n\n{text}")
            else:
                chunks.append(text)
        text = "\n\n".join(chunks)
        self.result_view.setPlainText(text)

    def _copy(self) -> None:
        if not self._results:
            return
        QApplication.clipboard().setText(self.result_view.toPlainText())
        self.status_lbl.setText("Copied transcript to clipboard.")

    def _save_txt(self) -> None:
        if not self._results:
            return
        suffix = "." + self.save_format.currentText().lower()
        try:
            if len(self._results) == 1:
                source, result = self._results[0]
                suggested = str(
                    Path(self.cfg.save_dir or Path.home()) / f"{Path(source).stem}{suffix}"
                )
                path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save transcript",
                    suggested,
                    f"{self.save_format.currentText()} (*{suffix})",
                )
                if not path:
                    return
                self._write_result(Path(path), result, suffix)
                self.status_lbl.setText(f"Saved to {path}")
            else:
                folder = QFileDialog.getExistingDirectory(
                    self,
                    "Save batch transcripts",
                    self.cfg.save_dir or str(Path.home()),
                )
                if not folder:
                    return
                for source, result in self._results:
                    self._write_result(
                        Path(folder) / f"{Path(source).stem}{suffix}",
                        result,
                        suffix,
                    )
                self.status_lbl.setText(f"Saved {len(self._results)} transcripts to {folder}")
        except Exception as exc:
            logging.exception("Save failed")
            QMessageBox.warning(self, "Save failed", str(exc))

    def _write_result(self, path: Path, result, suffix: str) -> None:
        if suffix == ".srt":
            text = result.to_srt()
        elif suffix == ".vtt":
            text = result.to_vtt()
        elif suffix == ".json":
            text = result.to_json()
        else:
            text = result.to_txt(with_timestamps=self.timestamps_box.isChecked())
        path.write_text(text, encoding="utf-8")

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(url.isLocalFile() for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())
        if paths:
            self._add_files(paths)
            self.cfg.file_last_dir = str(Path(paths[0]).parent)
            self.cfg.save()
            event.acceptProposedAction()
