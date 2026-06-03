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

        # Language — locked to PT-BR or EN. PT-BR keeps Whisper anchored to
        # Portuguese (no Japanese/Spanish hallucinations on silence) while the
        # bilingual prompt biases it to keep English terms spoken in the middle
        # of Portuguese sentences as English words.
        self._lang_codes = {
            "Portuguese (Brazil) + English terms": "pt-BR",
            "English":                              "en",
        }
        self.language = QComboBox()
        self.language.addItems(list(self._lang_codes.keys()))
        wanted = cfg.language if cfg.language in {"pt-BR", "en"} else "pt-BR"
        for label, code in self._lang_codes.items():
            if code == wanted:
                self.language.setCurrentText(label)
                break

        card.add_row(
            "Language",
            self.language,
            sub="Portuguese (Brazil) is locked to PT-BR but keeps English words spoken mid-sentence as English. Pick English only if dictating fully in English.",
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

        self.compute_device = QComboBox()
        self._device_options = {
            "Auto (GPU if available)": "auto",
            "CUDA GPU": "cuda",
            "CPU": "cpu",
        }
        self.compute_device.addItems(list(self._device_options.keys()))
        for label, value in self._device_options.items():
            if value == getattr(cfg, "compute_device", "auto"):
                self.compute_device.setCurrentText(label)
                break
        card.add_row(
            "Run on",
            self.compute_device,
            sub="Auto uses CUDA on NVIDIA GPUs when the CUDA runtime is available, then falls back to CPU.",
        )

        self.compute_type = QComboBox()
        self._compute_options = {
            "Float16 (fast GPU)":         "float16",
            "Int8 Float16 (lighter GPU)": "int8_float16",
            "Int8 (CPU / low VRAM)":      "int8",
        }
        self.compute_type.addItems(list(self._compute_options.keys()))
        legacy_compute = getattr(cfg, "compute_type", "float16")
        if legacy_compute == "float32":
            legacy_compute = "float16"
        for label, value in self._compute_options.items():
            if value == legacy_compute:
                self.compute_type.setCurrentText(label)
                break
        card.add_row("Precision", self.compute_type, sub="Float16 is the GPU default. Int8 variants are for CPU or very low VRAM.")
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
        self.compute_device.currentTextChanged.connect(self._save)
        self.compute_type.currentTextChanged.connect(self._save)
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
        for label, value in self._device_options.items():
            if self.compute_device.currentText() == label:
                self.cfg.compute_device = value
                break
        for label, value in self._compute_options.items():
            if self.compute_type.currentText() == label:
                self.cfg.compute_type = value
                break
        self.cfg.streaming = self.streaming_toggle.isChecked()
        self.cfg.save()
        self.config_changed.emit()
