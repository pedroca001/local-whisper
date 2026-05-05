from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QSlider, QVBoxLayout, QWidget

from ..widgets.card import Card
from ..widgets.toggle_switch import ToggleSwitch
from ...audio import list_input_devices, list_output_devices
from ...config import Config


class SoundPage(QWidget):
    config_changed = Signal()

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(14)

        title = QLabel("Sound")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)
        sub = QLabel("Microphone, playback and feedback sounds.")
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        v.addWidget(sub)

        # Microphone card
        mic_card = Card()
        mic_card.add_title("Microphone")
        self.device = QComboBox()
        self.device.addItem("System default microphone", userData=None)
        for d in list_input_devices():
            self.device.addItem(d["name"], userData=d["index"])
        # Match saved
        if cfg.input_device:
            for i in range(self.device.count()):
                if self.device.itemText(i) == cfg.input_device:
                    self.device.setCurrentIndex(i)
                    break
        mic_card.add_row("Input device", self.device)

        self.mic_boost = ToggleSwitch(checked=cfg.auto_mic_boost)
        mic_card.add_row("Automatically increase microphone volume", self.mic_boost)

        self.silence = ToggleSwitch(checked=cfg.silence_removal)
        mic_card.add_row("Silence removal (VAD)", self.silence)
        v.addWidget(mic_card)

        # Sound effects
        sfx_card = Card()
        sfx_card.add_title("Sound Effects")
        self.sfx = ToggleSwitch(checked=cfg.sound_effects)
        sfx_card.add_row("Enable sound effects", self.sfx)

        self.output_device = QComboBox()
        self.output_device.addItem("System default output", userData=None)
        for d in list_output_devices():
            self.output_device.addItem(d["name"], userData=d["index"])
        if cfg.output_device:
            for i in range(self.output_device.count()):
                if self.output_device.itemText(i) == cfg.output_device:
                    self.output_device.setCurrentIndex(i)
                    break
        sfx_card.add_row("Output device", self.output_device)

        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(int(cfg.sound_volume * 100))
        self.vol.setMaximumWidth(160)
        sfx_card.add_row("Volume", self.vol)
        v.addWidget(sfx_card)
        v.addStretch(1)

        self.device.currentIndexChanged.connect(self._save)
        self.mic_boost.toggled_changed.connect(self._save)
        self.silence.toggled_changed.connect(self._save)
        self.sfx.toggled_changed.connect(self._save)
        self.output_device.currentIndexChanged.connect(self._save)
        self.vol.valueChanged.connect(self._save)

    def _save(self, *args):
        text = self.device.currentText()
        self.cfg.input_device = None if text == "System default microphone" else text
        self.cfg.auto_mic_boost = self.mic_boost.isChecked()
        self.cfg.silence_removal = self.silence.isChecked()
        self.cfg.sound_effects = self.sfx.isChecked()
        out_text = self.output_device.currentText()
        self.cfg.output_device = None if out_text == "System default output" else out_text
        self.cfg.sound_volume = self.vol.value() / 100.0
        self.cfg.save()
        self.config_changed.emit()
