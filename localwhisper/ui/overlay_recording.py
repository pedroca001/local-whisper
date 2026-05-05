"""Top-center frameless recording overlay (macOS Spotlight-inspired)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont, QGuiApplication, QBrush
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame

from .widgets.waveform import WaveformWidget


class KeyChip(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            "background: rgba(255,255,255,28); color: rgba(255,255,255,200);"
            "border: 1px solid rgba(255,255,255,40); border-radius: 5px;"
            "padding: 1px 7px; font-size: 11px; font-weight: 600;"
        )


class RecordingOverlay(QWidget):
    """Frameless rounded overlay shown at top-center while recording.

    Does not steal focus, stays on top, transparent corners.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)

        self.setFixedSize(440, 64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 14, 10)
        layout.setSpacing(10)

        self.mic_label = QLabel("🎙")
        self.mic_label.setStyleSheet("color: rgba(255,255,255,210); font-size: 14px;")
        layout.addWidget(self.mic_label)

        self.device_label = QLabel("Default")
        self.device_label.setStyleSheet("color: rgba(255,255,255,220); font-size: 12px;")
        layout.addWidget(self.device_label)

        self.waveform = WaveformWidget(self, color=QColor(255, 255, 255, 200))
        layout.addWidget(self.waveform, stretch=1)

        # "Stop ⌃Space"
        stop_box = QHBoxLayout()
        stop_box.setSpacing(4)
        stop_lbl = QLabel("Stop")
        stop_lbl.setStyleSheet("color: rgba(255,255,255,200); font-size: 12px;")
        stop_box.addWidget(stop_lbl)
        self.stop_chip_ctrl = KeyChip("Ctrl")
        self.stop_chip_space = KeyChip("Space")
        stop_box.addWidget(self.stop_chip_ctrl)
        stop_box.addWidget(self.stop_chip_space)
        wrap1 = QFrame()
        wrap1.setLayout(stop_box)
        layout.addWidget(wrap1)

        cancel_box = QHBoxLayout()
        cancel_box.setSpacing(4)
        cancel_lbl = QLabel("Cancel")
        cancel_lbl.setStyleSheet("color: rgba(255,255,255,200); font-size: 12px;")
        cancel_box.addWidget(cancel_lbl)
        self.cancel_chip = KeyChip("Esc")
        cancel_box.addWidget(self.cancel_chip)
        wrap2 = QFrame()
        wrap2.setLayout(cancel_box)
        layout.addWidget(wrap2)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(180)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

    def update_hotkey(self, hotkey: str) -> None:
        parts = [p.strip().capitalize() for p in hotkey.split("+") if p.strip()]
        if len(parts) >= 2:
            mods = " ".join(parts[:-1])
            key = parts[-1]
            self.stop_chip_ctrl.setText(mods)
            self.stop_chip_space.setText(key)

    def update_device(self, name: str) -> None:
        self.device_label.setText(name or "Default")

    def set_audio_level(self, level: float) -> None:
        self.waveform.set_level(level)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        rect = QRectF(0, 0, self.width(), self.height())
        path.addRoundedRect(rect, 14, 14)
        # Dark glass background
        p.fillPath(path, QBrush(QColor(28, 28, 30, 235)))
        # Subtle border
        p.setPen(QColor(255, 255, 255, 22))
        p.drawPath(path)
        p.end()

    def _disconnect_anim_finished(self) -> None:
        try:
            self._opacity_anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass

    def show_at_top_center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.left() + (geo.width() - self.width()) // 2
        y = geo.top() + 28
        self.move(x, y)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._opacity_anim.stop()
        # Critical: clear any 'hide' connection left over from a previous fade-out,
        # otherwise the fade-in animation will trigger that hide() at its end.
        self._disconnect_anim_finished()
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()

    def fade_out_and_hide(self) -> None:
        self._opacity_anim.stop()
        self._disconnect_anim_finished()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.finished.connect(self.hide)
        self._opacity_anim.start()
