"""Reusable rounded card container."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def add_row(self, label_text: str, widget: QWidget, sub: str | None = None) -> None:
        if self._layout.count() > 0:
            sep = QFrame()
            sep.setObjectName("CardSeparator")
            sep.setFrameShape(QFrame.HLine)
            self._layout.addWidget(sep)
        row = QWidget()
        row_l = QVBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(0)

        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        lbl.setObjectName("CardRowLabel")
        line.addWidget(lbl)
        line.addStretch(1)
        line.addSpacing(8)
        line.addWidget(widget)
        line.setContentsMargins(0, 0, 16, 0)
        wrap = QWidget()
        wrap.setLayout(line)
        row_l.addWidget(wrap)

        if sub:
            s = QLabel(sub)
            s.setObjectName("CardRowSub")
            s.setWordWrap(True)
            row_l.addWidget(s)

        self._layout.addWidget(row)

    def add_widget(self, widget: QWidget) -> None:
        if self._layout.count() > 0:
            sep = QFrame()
            sep.setObjectName("CardSeparator")
            sep.setFrameShape(QFrame.HLine)
            self._layout.addWidget(sep)
        self._layout.addWidget(widget)

    def add_title(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("CardTitle")
        self._layout.addWidget(lbl)
