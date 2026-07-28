from __future__ import annotations

import json

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...doctor import run_doctor
from ..widgets.card import Card


class _DoctorWorker(QObject):
    finished = Signal(dict)

    def run(self) -> None:
        self.finished.emit(run_doctor())


class DiagnosticsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: dict = {}
        self._thread: QThread | None = None
        self._worker: _DoctorWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 16, 28, 28)
        layout.setSpacing(14)

        title = QLabel("Diagnostics")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "A private, read-only health report for models, CUDA, FFmpeg, storage and dependencies."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        status_card = Card()
        status_card.add_title("System health")
        self.overall = QLabel("Not checked yet")
        self.overall.setObjectName("Pill")
        status_card.add_row("Overall", self.overall)
        self.cuda = QLabel("—")
        status_card.add_row("CUDA", self.cuda)
        self.ffmpeg = QLabel("—")
        status_card.add_row("FFmpeg", self.ffmpeg)
        self.storage = QLabel("—")
        status_card.add_row("Local storage", self.storage)
        layout.addWidget(status_card)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(240)
        self.details.setPlaceholderText("Run diagnostics to generate a redacted report.")
        layout.addWidget(self.details, stretch=1)

        buttons = QHBoxLayout()
        refresh = QPushButton("Run diagnostics")
        refresh.setObjectName("PrimaryButton")
        refresh.clicked.connect(self.refresh)
        self.copy = QPushButton("Copy report")
        self.copy.setEnabled(False)
        self.copy.clicked.connect(self._copy)
        self.save = QPushButton("Save report…")
        self.save.setEnabled(False)
        self.save.clicked.connect(self._save)
        buttons.addStretch(1)
        buttons.addWidget(self.copy)
        buttons.addWidget(self.save)
        buttons.addWidget(refresh)
        layout.addLayout(buttons)

    def refresh(self) -> None:
        if self._thread is not None:
            return
        self.overall.setText("Checking…")
        self._thread = QThread(self)
        self._worker = _DoctorWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_result)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _on_result(self, result: dict) -> None:
        self._result = result
        checks = result.get("checks", {})
        self.overall.setText("Ready" if result.get("ok") else "Needs attention")
        self.overall.setObjectName("PillGood" if result.get("ok") else "Pill")
        self.overall.style().unpolish(self.overall)
        self.overall.style().polish(self.overall)
        cuda = checks.get("cuda", {})
        self.cuda.setText(
            f"{cuda.get('device_count', 0)} CUDA device(s)"
            if cuda.get("ok")
            else f"Unavailable: {cuda.get('error') or 'no CUDA device'}"
        )
        ffmpeg = checks.get("ffmpeg", {})
        self.ffmpeg.setText(str(ffmpeg.get("path") or "Not found"))
        history = checks.get("history", {})
        self.storage.setText("Writable and healthy" if history.get("ok") else str(history.get("error")))
        self.details.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.copy.setEnabled(True)
        self.save.setEnabled(True)

    def _cleanup(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None

    def _copy(self) -> None:
        if self._result:
            QGuiApplication.clipboard().setText(
                json.dumps(self._result, ensure_ascii=False, indent=2)
            )

    def _save(self) -> None:
        if not self._result:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save LocalWhisper diagnostic report",
            "localwhisper-diagnostics.json",
            "JSON (*.json)",
        )
        if path:
            from pathlib import Path

            Path(path).write_text(
                json.dumps(self._result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
