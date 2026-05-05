from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from ..widgets.card import Card
from ..widgets.toggle_switch import ToggleSwitch
from ...config import Config
from ...gpu import CUDA_TOOLKIT_URL, get_info as get_gpu_info
from ...transcriber import list_models


class ModesPage(QWidget):
    config_changed = Signal()

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(14)

        title = QLabel("Modes")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)

        gpu = get_gpu_info()
        sub_text = self._gpu_subtitle(gpu)
        sub = QLabel(sub_text)
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        sub.setOpenExternalLinks(True)
        sub.setWordWrap(True)
        v.addWidget(sub)

        card = Card()
        card.add_title("Default")

        # Preset
        self.preset = QComboBox()
        self.preset.addItems(["Voice", "Email", "Chat"])
        card.add_row("Preset", self.preset, sub="Tunes punctuation and formatting style.")

        # Language
        self._lang_codes = {
            "Multilingual (auto-detect)": "auto",
            "Portuguese (Brazil)":        "pt-BR",
            "Portuguese (Portugal)":      "pt-PT",
            "English":                    "en",
            "Spanish":                    "es",
            "French":                     "fr",
            "German":                     "de",
            "Italian":                    "it",
        }
        self.language = QComboBox()
        self.language.addItems(list(self._lang_codes.keys()))
        wanted = "pt-BR" if cfg.language == "pt" else cfg.language
        for label, code in self._lang_codes.items():
            if code == wanted:
                self.language.setCurrentText(label)
                break

        card.add_row(
            "Language",
            self.language,
            sub="'Multilingual' detects the spoken language automatically — ideal if you mix languages in the same dictation.",
        )

        # Voice model — label each entry with GPU/CPU indicator
        self.voice_model = QComboBox()
        self._models = list_models()
        for m in self._models:
            label = self._model_label(m, gpu)
            self.voice_model.addItem(label, userData=m["key"])
        for i in range(self.voice_model.count()):
            if self.voice_model.itemData(i) == cfg.model:
                self.voice_model.setCurrentIndex(i)
                break

        card.add_row("Voice Model", self.voice_model, sub=self._model_subtitle(cfg.model, gpu))
        v.addWidget(card)

        # Streaming card
        card2 = Card()
        card2.add_title("Streaming")
        self.streaming_toggle = ToggleSwitch(checked=cfg.streaming)
        card2.add_row(
            "Live streaming injection",
            self.streaming_toggle,
            sub="If on, words appear as you speak (with small refinements). If off, the full text is typed when you press the hotkey again.",
        )
        v.addWidget(card2)
        v.addStretch(1)

        self.preset.currentTextChanged.connect(self._save)
        self.language.currentTextChanged.connect(self._save)
        self.voice_model.currentIndexChanged.connect(self._model_changed)
        self.streaming_toggle.toggled_changed.connect(self._save)

        self._model_sub_label: QLabel | None = None

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _gpu_subtitle(gpu) -> str:
        if gpu is None:
            return "No NVIDIA GPU detected — all models run on CPU."
        if gpu.cuda_ready:
            return (
                f"GPU: {gpu.name} ({gpu.vram_label} VRAM) — "
                "GPU acceleration active. Models run locally on your GPU."
            )
        return (
            f"GPU: {gpu.name} ({gpu.vram_label} VRAM) detected, but "
            f"<b>CUDA Toolkit 12 is not installed</b> — models will run on CPU. "
            f'<a href="{CUDA_TOOLKIT_URL}">Download CUDA Toolkit</a> to enable GPU.'
        )

    @staticmethod
    def _model_label(m: dict, gpu) -> str:
        """Build the combobox label: name — VRAM requirement — GPU or CPU badge."""
        cuda_ready = gpu is not None and gpu.cuda_ready
        fits_in_vram = cuda_ready and (gpu.vram_gb >= m["approx_vram_gb"])
        badge = "GPU" if fits_in_vram else "CPU"
        return f"{m['display_name']}  —  ~{m['approx_vram_gb']}GB  [{badge}]"

    def _model_subtitle(self, key: str, gpu) -> str:
        for m in self._models:
            if m["key"] == key:
                cuda_ready = gpu is not None and gpu.cuda_ready
                fits = cuda_ready and (gpu.vram_gb >= m["approx_vram_gb"])
                device_note = (
                    f"GPU (~{m['speed_x_realtime']}x real-time)"
                    if fits
                    else f"CPU (int8, ~5x real-time)"
                )
                return f"{m['subtitle']} • {device_note}"
        return ""

    # ── slots ─────────────────────────────────────────────────────────────────

    def _model_changed(self, _index: int) -> None:
        self._save()

    def _save(self, *args):
        for label, code in self._lang_codes.items():
            if self.language.currentText() == label:
                self.cfg.language = code
                break
        key = self.voice_model.currentData()
        if key:
            self.cfg.model = key
        self.cfg.streaming = self.streaming_toggle.isChecked()
        self.cfg.save()
        self.config_changed.emit()
