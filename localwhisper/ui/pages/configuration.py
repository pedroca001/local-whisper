from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..widgets.card import Card
from ..widgets.toggle_switch import ToggleSwitch
from ...config import Config


class HotkeyCapture(QLineEdit):
    """A QLineEdit-like widget that captures the next key combination pressed."""

    captured = Signal(str)

    def __init__(self, current: str = "ctrl+space", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setText(current)
        self._capturing = False
        self.setPlaceholderText("Click to record")

    def mousePressEvent(self, event):
        self._capturing = True
        self.setText("Press a key combination…")
        self.setStyleSheet("color: #007aff;")

    def keyPressEvent(self, event: QKeyEvent):
        if not self._capturing:
            return super().keyPressEvent(event)
        mods = event.modifiers()
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return  # wait for non-modifier
        parts = []
        if mods & Qt.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.AltModifier:
            parts.append("alt")
        if mods & Qt.ShiftModifier:
            parts.append("shift")
        if mods & Qt.MetaModifier:
            parts.append("win")
        # Map key
        if Qt.Key_A <= key <= Qt.Key_Z:
            parts.append(chr(key).lower())
        elif Qt.Key_0 <= key <= Qt.Key_9:
            parts.append(chr(key))
        elif key == Qt.Key_Space:
            parts.append("space")
        elif key == Qt.Key_Escape:
            parts.append("esc")
        elif Qt.Key_F1 <= key <= Qt.Key_F12:
            parts.append(f"f{key - Qt.Key_F1 + 1}")
        else:
            return
        combo = "+".join(parts)
        self.setText(combo)
        self._capturing = False
        self.setStyleSheet("")
        self.captured.emit(combo)


class ConfigurationPage(QWidget):
    hotkey_changed = Signal(str)
    config_changed = Signal()

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(14)

        title = QLabel("Configuration")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)
        sub = QLabel("Hotkeys, save folder, and launch behavior.")
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        v.addWidget(sub)

        card = Card()
        card.add_title("Keyboard Shortcuts")

        self.toggle_hk = HotkeyCapture(cfg.hotkey_toggle)
        self.toggle_hk.setMaximumWidth(180)
        self.toggle_hk.captured.connect(self._on_hotkey_captured)
        card.add_row(
            "Toggle recording",
            self.toggle_hk,
            sub="Starts and stops recording. If the chosen combination is already in use by another app, the registration will fail and you can pick another.",
        )

        self.cancel_hk = QLineEdit("Esc")
        self.cancel_hk.setReadOnly(True)
        self.cancel_hk.setMaximumWidth(180)
        card.add_row("Cancel recording", self.cancel_hk, sub="Discards the active recording.")

        v.addWidget(card)

        # Save folder
        card2 = Card()
        card2.add_title("Storage")
        self.save_dir = QLineEdit(cfg.save_dir)
        self.save_dir.setMinimumWidth(280)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_dir)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(self.save_dir)
        wl.addWidget(browse)
        card2.add_row("Save folder", wrap, sub="Plain-text transcriptions are mirrored here, one file per day.")

        self.auto_launch = ToggleSwitch(checked=cfg.auto_launch)
        self.auto_launch.toggled_changed.connect(self._on_auto_launch)
        card2.add_row("Launch on Windows startup", self.auto_launch)
        v.addWidget(card2)

        v.addStretch(1)

        self.save_dir.editingFinished.connect(self._save)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select save folder", self.cfg.save_dir)
        if d:
            self.save_dir.setText(d)
            self._save()

    def _on_hotkey_captured(self, combo: str):
        self.cfg.hotkey_toggle = combo
        self.cfg.save()
        self.hotkey_changed.emit(combo)

    def _on_auto_launch(self, on: bool):
        self.cfg.auto_launch = on
        self.cfg.save()
        try:
            from ...autostart import set_auto_launch

            set_auto_launch(on)
        except Exception:
            pass

    def _save(self):
        self.cfg.save_dir = self.save_dir.text().strip() or self.cfg.save_dir
        self.cfg.save()
        self.config_changed.emit()
