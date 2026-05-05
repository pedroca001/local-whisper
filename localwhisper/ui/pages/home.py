from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QPushButton, QHBoxLayout

from ..widgets.card import Card
from ...config import Config


class HomePage(QWidget):
    def __init__(self, cfg: Config, on_record_now=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.on_record_now = on_record_now

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(16)

        title = QLabel("Home")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)

        sub = QLabel("Press your hotkey anywhere on Windows to start dictating.")
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        v.addWidget(sub)

        card = Card()
        card.add_title("Quick info")

        row = QWidget()
        rl = QVBoxLayout(row)
        rl.setContentsMargins(18, 8, 18, 14)
        rl.setSpacing(6)
        self.lbl_hotkey = QLabel(self._fmt_hotkey())
        self.lbl_model = QLabel(f"Model: {cfg.model}")
        self.lbl_lang = QLabel(f"Language: {cfg.language.upper()}")
        for lbl in (self.lbl_hotkey, self.lbl_model, self.lbl_lang):
            lbl.setStyleSheet("color: #3a3a3c;")
            rl.addWidget(lbl)
        card.add_widget(row)
        v.addWidget(card)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn = QPushButton("Record manually")
        btn.setObjectName("PrimaryButton")
        btn.clicked.connect(lambda: self.on_record_now and self.on_record_now())
        btn_row.addWidget(btn)
        v.addLayout(btn_row)
        v.addStretch(1)

    def _fmt_hotkey(self) -> str:
        parts = [p.capitalize() for p in self.cfg.hotkey_toggle.split("+")]
        return f"Hotkey: {' + '.join(parts)}"

    def refresh(self) -> None:
        self.lbl_hotkey.setText(self._fmt_hotkey())
        self.lbl_model.setText(f"Model: {self.cfg.model}")
        self.lbl_lang.setText(f"Language: {self.cfg.language.upper()}")
