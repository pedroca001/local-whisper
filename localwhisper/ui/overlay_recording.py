"""Top-center recording/result overlay."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "recording"
        self._set_recording_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)

        self.recording_page = self._build_recording_page()
        self.result_page = self._build_result_page()
        self.stack.addWidget(self.recording_page)
        self.stack.addWidget(self.result_page)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(180)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hide_after_fade_connected = False

    def _build_recording_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(18, 10, 14, 10)
        layout.setSpacing(10)

        self.mic_label = QLabel("Mic")
        self.mic_label.setStyleSheet("color: rgba(255,255,255,210); font-size: 12px; font-weight: 700;")
        layout.addWidget(self.mic_label)

        self.device_label = QLabel("Default")
        self.device_label.setStyleSheet("color: rgba(255,255,255,220); font-size: 12px;")
        layout.addWidget(self.device_label)

        self.waveform = WaveformWidget(self, color=QColor(255, 255, 255, 200))
        layout.addWidget(self.waveform, stretch=1)

        stop_box = QHBoxLayout()
        stop_box.setSpacing(4)
        stop_lbl = QLabel("Stop")
        stop_lbl.setStyleSheet("color: rgba(255,255,255,200); font-size: 12px;")
        stop_box.addWidget(stop_lbl)
        self.stop_chip_ctrl = KeyChip("Ctrl")
        self.stop_chip_space = KeyChip("Space")
        stop_box.addWidget(self.stop_chip_ctrl)
        stop_box.addWidget(self.stop_chip_space)
        stop_wrap = QFrame()
        stop_wrap.setLayout(stop_box)
        layout.addWidget(stop_wrap)

        cancel_box = QHBoxLayout()
        cancel_box.setSpacing(4)
        cancel_lbl = QLabel("Cancel")
        cancel_lbl.setStyleSheet("color: rgba(255,255,255,200); font-size: 12px;")
        cancel_box.addWidget(cancel_lbl)
        self.cancel_chip = KeyChip("Esc")
        cancel_box.addWidget(self.cancel_chip)
        cancel_wrap = QFrame()
        cancel_wrap.setLayout(cancel_box)
        layout.addWidget(cancel_wrap)

        return page

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setAcceptRichText(False)
        self.result_text.setStyleSheet(
            "QTextEdit {"
            "background: rgba(255,255,255,18); color: rgba(255,255,255,235);"
            "border: 1px solid rgba(255,255,255,36); border-radius: 6px;"
            "padding: 8px; font-size: 13px; selection-background-color: #2f7cf6;"
            "}"
        )
        layout.addWidget(self.result_text)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)

        self.copy_all_btn = QPushButton("Copiar tudo")
        self.copy_all_btn.setCursor(Qt.PointingHandCursor)
        self.copy_all_btn.setStyleSheet(
            "QPushButton {"
            "background: rgba(47,124,246,220); color: white;"
            "border: 1px solid rgba(47,124,246,255); border-radius: 6px;"
            "padding: 6px 16px; font-size: 12px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: rgba(47,124,246,255); }"
            "QPushButton:pressed { background: rgba(36,100,205,255); }"
        )
        self.copy_all_btn.clicked.connect(self._copy_all_and_close)
        actions.addWidget(self.copy_all_btn)

        layout.addLayout(actions)
        return page

    def _copy_all_and_close(self) -> None:
        text = self.result_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
        self.dismiss_result()

    def dismiss_result(self) -> None:
        self._opacity_anim.stop()
        self._disconnect_anim_finished()
        self.result_text.clear()
        self._mode = "recording"
        self.hide()
        self.setWindowOpacity(1.0)

    def _set_recording_flags(self) -> None:
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setFocusPolicy(Qt.NoFocus)

    def _set_result_flags(self) -> None:
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFocusPolicy(Qt.StrongFocus)

    def update_hotkey(self, hotkey: str) -> None:
        parts = [p.strip().capitalize() for p in hotkey.split("+") if p.strip()]
        if len(parts) >= 2:
            self.stop_chip_ctrl.setText(" ".join(parts[:-1]))
            self.stop_chip_space.setText(parts[-1])

    def update_cancel_hotkey(self, hotkey: str) -> None:
        text = " ".join(p.strip().capitalize() for p in hotkey.split("+") if p.strip())
        self.cancel_chip.setText(text or "Esc")

    def update_device(self, name: str) -> None:
        self.device_label.setText(name or "Default")

    def set_audio_level(self, level: float) -> None:
        self.waveform.set_level(level)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        rect = QRectF(0, 0, self.width(), self.height())
        radius = 14 if self._mode == "recording" else 10
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, QBrush(QColor(28, 28, 30, 240)))
        p.setPen(QColor(255, 255, 255, 28))
        p.drawPath(path)
        p.end()

    def _disconnect_anim_finished(self) -> None:
        if not self._hide_after_fade_connected:
            return
        try:
            self._opacity_anim.finished.disconnect(self._hide_after_fade)
        except (RuntimeError, TypeError):
            pass
        self._hide_after_fade_connected = False

    def _hide_after_fade(self) -> None:
        self._disconnect_anim_finished()
        self.hide()

    def _move_top_center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.left() + (geo.width() - self.width()) // 2
        y = geo.top() + 28
        self.move(x, y)

    def show_at_top_center(self) -> None:
        self._mode = "recording"
        self.hide()
        self._set_recording_flags()
        self.stack.setCurrentWidget(self.recording_page)
        self.setFixedSize(440, 64)
        self._move_top_center()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._opacity_anim.stop()
        self._disconnect_anim_finished()
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()

    def show_result_text(self, text: str) -> None:
        if not text.strip():
            return
        self._mode = "result"
        self.hide()
        self._opacity_anim.stop()
        self._disconnect_anim_finished()
        self._set_result_flags()
        self.stack.setCurrentWidget(self.result_page)
        self.result_text.setPlainText(text.strip())
        line_count = max(2, min(8, text.count("\n") + len(text) // 80 + 1))
        # 74px = chrome + paddings; +24px per text line; +44px for the button row
        self.setFixedSize(640, min(360, 118 + line_count * 24))
        self._move_top_center()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self.repaint()
        self.activateWindow()
        self.result_text.setFocus(Qt.OtherFocusReason)
        self.result_text.selectAll()

    def fade_out_and_hide(self) -> None:
        if self._mode == "result":
            self.dismiss_result()
            return
        self._opacity_anim.stop()
        self._disconnect_anim_finished()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.finished.connect(self._hide_after_fade)
        self._hide_after_fade_connected = True
        self._opacity_anim.start()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self._mode == "result":
            QTimer.singleShot(120, self._hide_result_if_unfocused)

    def _hide_result_if_unfocused(self) -> None:
        if self._mode != "result":
            return
        focus = QApplication.focusWidget()
        if focus is None or (focus is not self and not self.isAncestorOf(focus)):
            self.hide()
