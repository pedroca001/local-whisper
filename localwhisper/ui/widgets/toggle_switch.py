"""iOS/macOS-style toggle switch."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    toggled_changed = Signal(bool)

    def __init__(self, parent=None, checked: bool = False):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(40, 22)
        self._handle_pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"handlePos", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._on_toggled)

    def sizeHint(self) -> QSize:
        return QSize(40, 22)

    def _on_toggled(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._handle_pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()
        self.toggled_changed.emit(on)

    def get_handle_pos(self) -> float:
        return self._handle_pos

    def set_handle_pos(self, v: float) -> None:
        self._handle_pos = v
        self.update()

    handlePos = Property(float, get_handle_pos, set_handle_pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        bg_off = QColor(220, 220, 224)
        bg_on = QColor(52, 199, 89)  # macOS green
        bg = QColor(
            int(bg_off.red() + (bg_on.red() - bg_off.red()) * self._handle_pos),
            int(bg_off.green() + (bg_on.green() - bg_off.green()) * self._handle_pos),
            int(bg_off.blue() + (bg_on.blue() - bg_off.blue()) * self._handle_pos),
        )
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        knob_d = rect.height() - 4
        knob_x = rect.x() + 2 + (rect.width() - knob_d - 4) * self._handle_pos
        knob_y = rect.y() + 2
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(int(knob_x), int(knob_y), int(knob_d), int(knob_d))
        p.end()
