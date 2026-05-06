"""UI page: pick an audio/video file, transcribe it (optionally with speaker diarization).

The heavy work runs on a QThread so the UI stays responsive. Progress and the
final transcript come back via Qt signals.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..widgets.card import Card
from ...config import Config


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

    def __init__(
        self,
        path: str,
        model_key: str,
        language: str,
        diarize: bool,
        hf_token: str,
        min_speakers: Optional[int],
        max_speakers: Optional[int],
    ):
        super().__init__()
        self.path = path
        self.model_key = model_key
        self.language = language
        self.diarize = diarize
        self.hf_token = hf_token
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers

    def run(self) -> None:
        try:
            # Lazy imports keep app startup fast — these pull in faster-whisper, ffmpeg, etc.
            from ...transcriber import get_engine
            from ...transcriber.file_transcriber import transcribe_file

            self.progress.emit("Loading speech model…", 0.02)
            engine = get_engine(self.model_key)
            engine.load()

            result = transcribe_file(
                self.path,
                engine=engine,
                language=self.language,
                diarize=self.diarize,
                hf_token=self.hf_token or None,
                min_speakers=self.min_speakers,
                max_speakers=self.max_speakers,
                on_progress=lambda label, pct: self.progress.emit(label, pct),
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            logging.exception("File transcription failed")
            self.failed.emit(str(exc))


# ─── page ──────────────────────────────────────────────────────────────────
class TranscribeFilePage(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._result = None  # FileTranscript

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(14)

        title = QLabel("Transcribe File")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)

        sub = QLabel(
            "Pick an audio or video file from your computer, choose the language, "
            "and (optionally) identify who is speaking."
        )
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        sub.setWordWrap(True)
        v.addWidget(sub)

        # ── File picker ────────────────────────────────────────────────
        card1 = Card()
        card1.add_title("File")
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("No file selected")
        self.path_edit.setReadOnly(True)
        self.path_edit.setMinimumWidth(260)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_file)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(self.path_edit)
        wl.addWidget(browse)
        card1.add_row(
            "Audio/Video file",
            wrap,
            sub="Supports mp3, mp4, m4a, wav, mov, mkv, webm and most other formats (decoded with ffmpeg).",
        )
        v.addWidget(card1)

        # ── Options ────────────────────────────────────────────────────
        card2 = Card()
        card2.add_title("Options")

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
        card3.add_title("Run")
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
        self.status_lbl.setStyleSheet("color: #6e6e73; padding: 4px 18px;")
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
        card4.add_title("Transcript")

        self.result_view = QTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setMinimumHeight(220)
        self.result_view.setPlaceholderText("Your transcript will appear here.")
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
        self.timestamps_box = QCheckBox("Show timestamps")
        self.timestamps_box.toggled.connect(self._refresh_view)
        aw.addWidget(self.timestamps_box)
        aw.addStretch(1)
        aw.addWidget(self.copy_btn)
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
        path, _ = QFileDialog.getOpenFileName(self, "Select audio or video file", start_dir, SUPPORTED_FILTER)
        if not path:
            return
        self.path_edit.setText(path)
        self.cfg.file_last_dir = str(Path(path).parent)
        self.cfg.save()
        self.run_btn.setEnabled(True)
        self.status_lbl.setText(f"Ready: {Path(path).name}")

    def _selected_lang(self) -> str:
        return self._lang_codes.get(self.language.currentText(), "auto")

    # ── execution ─────────────────────────────────────────────────────
    def _start(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
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
        self.result_view.clear()
        self.progress.setValue(0)
        self.status_lbl.setText("Starting…")

        min_spk = self.min_spk.value() or None
        max_spk = self.max_spk.value() or None

        self._thread = QThread(self)
        self._worker = _Worker(
            path=path,
            model_key=self.cfg.model,
            language=self._selected_lang(),
            diarize=diarize,
            hf_token=self.cfg.hf_token,
            min_speakers=min_spk,
            max_speakers=max_spk,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cancel(self) -> None:
        # Best-effort: pyannote / faster-whisper don't support mid-run cancellation
        # cleanly. We at least disable the UI and let the worker run out.
        self.cancel_btn.setEnabled(False)
        self.status_lbl.setText("Cancellation requested — waiting for current step to finish…")

    def _on_progress(self, label: str, pct: float) -> None:
        self.status_lbl.setText(label)
        if pct < 0:
            self.progress.setRange(0, 0)
        else:
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 1000)
            self.progress.setValue(int(max(0.0, min(1.0, pct)) * 1000))

    def _on_finished_ok(self, result) -> None:
        self._result = result
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        n = result.num_speakers
        msg = f"Done — {result.duration_s:.1f}s of audio, {len(result.segments)} segment(s)"
        if result.diarized and n:
            msg += f", {n} speaker(s) detected"
        elif self.diarize_box.isChecked() and not result.diarized:
            msg += " — speaker identification was skipped"
        self.status_lbl.setText(msg)
        self._refresh_view()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.copy_btn.setEnabled(True)
        self.save_btn.setEnabled(True)

    def _on_failed(self, err: str) -> None:
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.status_lbl.setText(f"Failed: {err}")
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QMessageBox.warning(self, "Transcription failed", err)

    def _cleanup_thread(self) -> None:
        if self._thread is not None:
            self._thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None

    # ── output rendering ──────────────────────────────────────────────
    def _refresh_view(self) -> None:
        if not self._result:
            return
        text = self._result.to_txt(with_timestamps=self.timestamps_box.isChecked())
        self.result_view.setPlainText(text)

    def _copy(self) -> None:
        if not self._result:
            return
        text = self._result.to_txt(with_timestamps=self.timestamps_box.isChecked())
        QApplication.clipboard().setText(text)
        self.status_lbl.setText("Copied transcript to clipboard.")

    def _save_txt(self) -> None:
        if not self._result:
            return
        suggested_dir = self.cfg.save_dir or str(Path.home())
        src_name = Path(self.path_edit.text()).stem or "transcript"
        suggested = str(Path(suggested_dir) / f"{src_name}.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save transcript", suggested, "Text (*.txt)")
        if not path:
            return
        try:
            text = self._result.to_txt(with_timestamps=self.timestamps_box.isChecked())
            Path(path).write_text(text, encoding="utf-8")
            self.status_lbl.setText(f"Saved to {path}")
        except Exception as exc:
            logging.exception("Save failed")
            QMessageBox.warning(self, "Save failed", str(exc))
