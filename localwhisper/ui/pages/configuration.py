from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config import Config
from ..widgets.card import Card
from ..widgets.toggle_switch import ToggleSwitch


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
    paste_last_hotkey_changed = Signal(str)
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

        self.cancel_hk = HotkeyCapture(cfg.hotkey_cancel)
        self.cancel_hk.setMaximumWidth(180)
        self.cancel_hk.captured.connect(self._on_cancel_hotkey_captured)
        card.add_row("Cancel recording", self.cancel_hk, sub="Discards the active recording.")

        self.paste_last_hk = HotkeyCapture(cfg.hotkey_paste_last)
        self.paste_last_hk.setMaximumWidth(180)
        self.paste_last_hk.captured.connect(self._on_paste_last_hotkey_captured)
        card.add_row(
            "Paste last transcription",
            self.paste_last_hk,
            sub="Pastes the most recent transcription into whatever window has focus.",
        )

        v.addWidget(card)

        behavior = Card()
        behavior.add_title("Dictation behavior")

        self.activation_mode = QComboBox()
        self.activation_mode.addItem("Press once to start / stop", "toggle")
        self.activation_mode.addItem("Hold to talk", "push_to_talk")
        self.activation_mode.setCurrentIndex(
            max(0, self.activation_mode.findData(cfg.activation_mode))
        )
        self.activation_mode.currentIndexChanged.connect(self._save_behavior)
        behavior.add_row(
            "Activation",
            self.activation_mode,
            sub="Toggle is best for long dictation. Hold to talk is fastest for short messages.",
        )

        self.mode_combo = QComboBox()
        for mode in cfg.dictation_modes:
            self.mode_combo.addItem(
                str(mode.get("name") or mode.get("id") or "Mode"),
                str(mode.get("id") or "default"),
            )
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(cfg.active_mode_id)))
        self.mode_combo.currentIndexChanged.connect(self._save_behavior)
        behavior.add_row(
            "Default mode",
            self.mode_combo,
            sub="App-specific patterns can automatically select a more suitable mode.",
        )

        self.output_action = QComboBox()
        self.output_action.addItem("Insert at cursor", "insert")
        self.output_action.addItem("Insert and press Enter", "insert_enter")
        self.output_action.addItem("Copy to clipboard", "clipboard")
        self.output_action.addItem("Save to history only", "history")
        self.output_action.setCurrentIndex(max(0, self.output_action.findData(cfg.output_action)))
        self.output_action.currentIndexChanged.connect(self._save_behavior)
        behavior.add_row("Default output", self.output_action)

        self.overlay_mode = QComboBox()
        self.overlay_mode.addItem("Compact overlay", "compact")
        self.overlay_mode.addItem("Full overlay", "full")
        self.overlay_mode.addItem("Audio feedback only", "hidden")
        self.overlay_mode.setCurrentIndex(max(0, self.overlay_mode.findData(cfg.overlay_mode)))
        self.overlay_mode.currentIndexChanged.connect(self._save_behavior)
        behavior.add_row("Recording feedback", self.overlay_mode)
        v.addWidget(behavior)

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

        self.private_mode = ToggleSwitch(checked=cfg.private_mode)
        self.private_mode.toggled_changed.connect(self._save_privacy)
        card2.add_row(
            "Private mode",
            self.private_mode,
            sub="Do not save new dictations to history or daily text files.",
        )

        self.retention_days = QSpinBox()
        self.retention_days.setRange(0, 3650)
        self.retention_days.setSpecialValueText("Keep forever")
        self.retention_days.setSuffix(" days")
        self.retention_days.setValue(cfg.history_retention_days)
        self.retention_days.valueChanged.connect(self._save_privacy)
        card2.add_row(
            "History retention",
            self.retention_days,
            sub="Favorites are always kept. Set to 0 to disable automatic cleanup.",
        )
        v.addWidget(card2)

        processing = Card()
        processing.add_title("Local text processing")

        self.remove_fillers = ToggleSwitch(checked=cfg.remove_filler_words)
        self.remove_fillers.toggled_changed.connect(self._save_processing)
        processing.add_row(
            "Remove hesitation sounds",
            self.remove_fillers,
            sub="Removes conservative filler sounds such as 'hum' and 'ahn'.",
        )

        self.spoken_commands = ToggleSwitch(checked=cfg.spoken_commands)
        self.spoken_commands.toggled_changed.connect(self._save_processing)
        processing.add_row(
            "Spoken formatting commands",
            self.spoken_commands,
            sub="Understands commands such as 'nova linha', 'novo parágrafo' and punctuation.",
        )

        self.smart_formatting = ToggleSwitch(checked=cfg.smart_formatting)
        self.smart_formatting.toggled_changed.connect(self._save_processing)
        processing.add_row("Clean spacing and capitalization", self.smart_formatting)

        self.max_session = QSpinBox()
        self.max_session.setRange(1, 120)
        self.max_session.setSuffix(" min")
        self.max_session.setValue(cfg.max_session_minutes)
        self.max_session.valueChanged.connect(self._save_processing)
        processing.add_row(
            "Maximum session",
            self.max_session,
            sub="Long sessions stop safely at this limit and keep the result recoverable.",
        )

        self.keep_warm = QSpinBox()
        self.keep_warm.setRange(0, 240)
        self.keep_warm.setSpecialValueText("Unload immediately")
        self.keep_warm.setSuffix(" min")
        self.keep_warm.setValue(cfg.model_keep_warm_minutes)
        self.keep_warm.valueChanged.connect(self._save_processing)
        processing.add_row(
            "Keep model ready",
            self.keep_warm,
            sub="Higher values reduce latency; lower values free GPU memory sooner.",
        )
        v.addWidget(processing)

        # HuggingFace token (for speaker diarization)
        card3 = Card()
        card3.add_title("Speaker diarization")
        self.hf_token = QLineEdit(cfg.hf_token or "")
        self.hf_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.hf_token.setPlaceholderText("hf_… (paste your HuggingFace access token)")
        self.hf_token.setMinimumWidth(280)
        self.hf_token.editingFinished.connect(self._save_token)
        card3.add_row(
            "HuggingFace token",
            self.hf_token,
            sub=(
                "Required only for the 'Transcribe File' speaker-identification feature. "
                "It's free: accept the model terms at huggingface.co/pyannote/speaker-diarization-3.1, "
                "then create a token at huggingface.co/settings/tokens. "
                "Encrypted for your Windows user with DPAPI."
            ),
        )
        v.addWidget(card3)

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

    def _on_cancel_hotkey_captured(self, combo: str):
        self.cfg.hotkey_cancel = combo
        self.cfg.save()
        self.config_changed.emit()

    def _on_paste_last_hotkey_captured(self, combo: str):
        self.cfg.hotkey_paste_last = combo
        self.cfg.save()
        self.paste_last_hotkey_changed.emit(combo)

    def _on_auto_launch(self, on: bool):
        self.cfg.auto_launch = on
        self.cfg.save()
        try:
            from ...autostart import set_auto_launch

            set_auto_launch(on)
        except Exception:
            pass

    def _save_behavior(self, *_args):
        self.cfg.activation_mode = str(self.activation_mode.currentData())
        self.cfg.active_mode_id = str(self.mode_combo.currentData())
        self.cfg.output_action = str(self.output_action.currentData())
        self.cfg.overlay_mode = str(self.overlay_mode.currentData())
        self.cfg.save()
        self.config_changed.emit()

    def _save_privacy(self, *_args):
        self.cfg.private_mode = self.private_mode.isChecked()
        self.cfg.history_retention_days = self.retention_days.value()
        self.cfg.save()
        self.config_changed.emit()

    def _save_processing(self, *_args):
        self.cfg.remove_filler_words = self.remove_fillers.isChecked()
        self.cfg.spoken_commands = self.spoken_commands.isChecked()
        self.cfg.smart_formatting = self.smart_formatting.isChecked()
        self.cfg.max_session_minutes = self.max_session.value()
        self.cfg.model_keep_warm_minutes = self.keep_warm.value()
        self.cfg.save()
        self.config_changed.emit()

    def _save(self):
        self.cfg.save_dir = self.save_dir.text().strip() or self.cfg.save_dir
        self.cfg.save()
        self.config_changed.emit()

    def _save_token(self):
        self.cfg.hf_token = self.hf_token.text().strip()
        self.cfg.save()
