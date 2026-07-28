"""Small first-run setup dialog."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..config import Config
from .widgets.card import Card


class OnboardingDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Welcome to LocalWhisper")
        self.setMinimumWidth(620)
        self.setModal(True)
        try:
            self.setStyleSheet(
                (Path(__file__).parent / "style.qss").read_text(encoding="utf-8")
            )
        except OSError:
            pass

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        kicker = QLabel("PRIVATE BY DESIGN")
        kicker.setObjectName("PageKicker")
        layout.addWidget(kicker)
        title = QLabel("Your voice, turned into text locally.")
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        subtitle = QLabel(
            "Choose the defaults below. You can change every option later; "
            "audio and transcripts never need to leave this computer."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        card = Card()
        card.add_title("Quick setup")
        self.language = QComboBox()
        self.language.addItem("Portuguese (Brazil) + English terms", "pt-BR")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(max(0, self.language.findData(cfg.language)))
        card.add_row("Dictation language", self.language)

        self.activation = QComboBox()
        self.activation.addItem("Press once to start, once to stop", "toggle")
        self.activation.addItem("Hold the hotkey while speaking", "push_to_talk")
        self.activation.setCurrentIndex(max(0, self.activation.findData(cfg.activation_mode)))
        card.add_row("Hotkey behavior", self.activation)

        self.streaming = QCheckBox("Show words while I speak")
        self.streaming.setChecked(cfg.streaming)
        card.add_row(
            "Live transcription",
            self.streaming,
            sub="Uses stable partial results and reconciles the final transcript safely.",
        )

        self.history = QCheckBox("Keep searchable local history")
        self.history.setChecked(not cfg.private_mode)
        card.add_row(
            "History",
            self.history,
            sub="Turn this off for private mode. Favorites are never removed by retention cleanup.",
        )
        layout.addWidget(card)

        tip = QLabel(
            f"After setup, press {self._format_hotkey(cfg.hotkey_toggle)} in any text field. "
            "Press Esc to cancel."
        )
        tip.setWordWrap(True)
        tip.setObjectName("PageSubtitle")
        layout.addWidget(tip)

        actions = QHBoxLayout()
        actions.addStretch(1)
        skip = QPushButton("Use recommended defaults")
        skip.clicked.connect(self._recommended)
        finish = QPushButton("Finish setup")
        finish.setObjectName("PrimaryButton")
        finish.clicked.connect(self._finish)
        actions.addWidget(skip)
        actions.addWidget(finish)
        layout.addLayout(actions)

    @staticmethod
    def _format_hotkey(value: str) -> str:
        return " + ".join(part.capitalize() for part in value.split("+") if part)

    def _recommended(self) -> None:
        self.language.setCurrentIndex(max(0, self.language.findData("pt-BR")))
        self.activation.setCurrentIndex(max(0, self.activation.findData("toggle")))
        self.streaming.setChecked(True)
        self.history.setChecked(True)
        self._finish()

    def _finish(self) -> None:
        self.cfg.language = str(self.language.currentData() or "pt-BR")
        self.cfg.activation_mode = str(self.activation.currentData() or "toggle")
        self.cfg.streaming = self.streaming.isChecked()
        self.cfg.private_mode = not self.history.isChecked()
        self.cfg.onboarding_complete = True
        self.cfg.save()
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)
