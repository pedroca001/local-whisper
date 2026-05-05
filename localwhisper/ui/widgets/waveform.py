"""Animated waveform widget — draws a centered VU-style bar pattern."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    def __init__(self, parent=None, color: QColor = QColor(120, 120, 130, 220)):
        super().__init__(parent)
        self.color = color
        self.setMinimumHeight(28)
        self._level = 0.0
        self._bars = 60
        self._phases = [random.random() * math.tau for _ in range(self._bars)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(33)  # ~30fps
        self._t0 = time.time()

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        cy = h / 2

        bar_w = max(1.5, w / (self._bars * 1.8))
        gap = bar_w * 0.8
        total_w = self._bars * bar_w + (self._bars - 1) * gap
        x0 = (w - total_w) / 2
        t = time.time() - self._t0

        pen = QPen(self.color)
        pen.setWidthF(bar_w)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)

        for i in range(self._bars):
            # Idle wave + level-driven amplitude
            phase = self._phases[i] + t * (2.0 + i * 0.05)
            base = 0.18 + 0.12 * math.sin(phase)
            amp = base + self._level * 0.85 * (0.4 + 0.6 * math.sin(phase * 1.7))
            bar_h = max(2.0, amp * (h * 0.85))
            x = x0 + i * (bar_w + gap)
            p.drawLine(int(x), int(cy - bar_h / 2), int(x), int(cy + bar_h / 2))
        p.end()
