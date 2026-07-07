from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...config import Config
from ..widgets.card import Card


class HomePage(QWidget):
    def __init__(self, cfg: Config, on_record_now=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.on_record_now = on_record_now

        v = QVBoxLayout(self)
        v.setContentsMargins(32, 24, 32, 30)
        v.setSpacing(18)

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(18)
        title_wrap = QWidget()
        tl = QVBoxLayout(title_wrap)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(4)
        kicker = QLabel("READY")
        kicker.setObjectName("PageKicker")
        title = QLabel("LocalWhisper")
        title.setObjectName("PageTitle")
        self.subtitle = QLabel(self._subtitle_text())
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setWordWrap(True)
        tl.addWidget(kicker)
        tl.addWidget(title)
        tl.addWidget(self.subtitle)
        hl.addWidget(title_wrap, stretch=1)

        btn = QPushButton("Record manually")
        btn.setObjectName("PrimaryButton")
        btn.setMinimumWidth(150)
        btn.clicked.connect(lambda: self.on_record_now and self.on_record_now())
        hl.addWidget(btn, alignment=Qt.AlignTop)
        v.addWidget(header)

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.metric_hotkey = self._metric("Hotkey", self._fmt_hotkey())
        self.metric_model = self._metric("Model", cfg.model)
        self.metric_language = self._metric("Language", self._fmt_language())
        self.metric_mode = self._metric("Insertion", self._fmt_streaming())
        metrics.addWidget(self.metric_hotkey, 0, 0)
        metrics.addWidget(self.metric_model, 0, 1)
        metrics.addWidget(self.metric_language, 1, 0)
        metrics.addWidget(self.metric_mode, 1, 1)
        v.addLayout(metrics)

        card = Card()
        card.add_title("Current setup")
        self.lbl_save_dir = QLabel(self.cfg.save_dir)
        self.lbl_save_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_paste_hotkey = QLabel(self._fmt_paste_hotkey())
        self.lbl_paste_hotkey.setObjectName("Pill")
        self.lbl_startup = QLabel(self._fmt_startup())
        self.lbl_startup.setObjectName("PillGood")
        card.add_row("Save folder", self.lbl_save_dir)
        card.add_row("Paste last", self.lbl_paste_hotkey)
        card.add_row("Startup", self.lbl_startup)
        v.addWidget(card)
        v.addStretch(1)

    def _metric(self, label: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("MetricCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(6)
        lbl = QLabel(label)
        lbl.setObjectName("MetricLabel")
        val = QLabel(value)
        val.setObjectName("MetricValue")
        val.setWordWrap(True)
        layout.addWidget(lbl)
        layout.addWidget(val)
        frame.value_label = val  # type: ignore[attr-defined]
        return frame

    def _fmt_hotkey(self) -> str:
        parts = [p.capitalize() for p in self.cfg.hotkey_toggle.split("+") if p]
        return " + ".join(parts)

    def _fmt_paste_hotkey(self) -> str:
        parts = [p.capitalize() for p in self.cfg.hotkey_paste_last.split("+") if p]
        return " + ".join(parts)

    def _fmt_language(self) -> str:
        return "Portuguese BR" if self.cfg.language == "pt-BR" else self.cfg.language.upper()

    def _fmt_streaming(self) -> str:
        return "Live streaming" if self.cfg.streaming else "After stop"

    def _fmt_startup(self) -> str:
        return "Enabled" if self.cfg.auto_launch else "Manual"

    def _subtitle_text(self) -> str:
        target = "live" if self.cfg.streaming else "on stop"
        return f"{self.cfg.model} dictation, {target} insertion, local history enabled."

    def refresh(self) -> None:
        self.metric_hotkey.value_label.setText(self._fmt_hotkey())  # type: ignore[attr-defined]
        self.metric_model.value_label.setText(self.cfg.model)  # type: ignore[attr-defined]
        self.metric_language.value_label.setText(self._fmt_language())  # type: ignore[attr-defined]
        self.metric_mode.value_label.setText(self._fmt_streaming())  # type: ignore[attr-defined]
        self.lbl_save_dir.setText(self.cfg.save_dir)
        self.lbl_paste_hotkey.setText(self._fmt_paste_hotkey())
        self.lbl_startup.setText(self._fmt_startup())
        self.subtitle.setText(self._subtitle_text())
