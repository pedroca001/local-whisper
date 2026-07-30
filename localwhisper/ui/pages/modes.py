from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...config import Config
from ...gpu import CUDA_TOOLKIT_URL
from ...gpu import get_info as get_gpu_info
from ...model_manager import install_model, list_model_status, uninstall_model
from ...transcriber import list_models
from ..widgets.card import Card
from ..widgets.toggle_switch import ToggleSwitch


class _ModelWorker(QObject):
    finished = Signal()
    failed = Signal(str)

    def __init__(self, action: str, key: str, models_dir: str, active_key: str):
        super().__init__()
        self.action = action
        self.key = key
        self.models_dir = models_dir
        self.active_key = active_key

    def run(self) -> None:
        try:
            if self.action == "install":
                install_model(self.key, self.models_dir)
            elif self.action == "uninstall":
                uninstall_model(self.key, self.models_dir, self.active_key)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


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

        # Writing profile
        self.preset = QComboBox()
        for mode in cfg.dictation_modes:
            self.preset.addItem(str(mode.get("name") or mode.get("id")), str(mode.get("id")))
        self.preset.setCurrentIndex(max(0, self.preset.findData(cfg.active_mode_id)))
        preset_wrap = QWidget()
        preset_layout = QHBoxLayout(preset_wrap)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(6)
        preset_layout.addWidget(self.preset, stretch=1)
        add_mode = QPushButton("New")
        add_mode.clicked.connect(self._create_mode)
        duplicate_mode = QPushButton("Duplicate")
        duplicate_mode.clicked.connect(self._duplicate_mode)
        delete_mode = QPushButton("Delete")
        delete_mode.setObjectName("DangerButton")
        delete_mode.clicked.connect(self._delete_mode)
        preset_layout.addWidget(add_mode)
        preset_layout.addWidget(duplicate_mode)
        preset_layout.addWidget(delete_mode)
        card.add_row(
            "Writing profile",
            preset_wrap,
            sub="Create focused profiles that activate automatically from the current app.",
        )

        self.mode_apps = QLineEdit()
        self.mode_apps.setPlaceholderText("outlook, gmail, slack")
        card.add_row(
            "Auto-activate in",
            self.mode_apps,
            sub="Comma-separated process names or window-title fragments.",
        )

        self.mode_output = QComboBox()
        self.mode_output.addItem("Use default output", "default")
        self.mode_output.addItem("Insert at cursor", "insert")
        self.mode_output.addItem("Insert and press Enter", "insert_enter")
        self.mode_output.addItem("Copy to clipboard", "clipboard")
        self.mode_output.addItem("Save to history only", "history")
        card.add_row("Output action", self.mode_output)

        self.mode_fillers = ToggleSwitch()
        card.add_row("Remove hesitation sounds", self.mode_fillers)
        self.mode_commands = ToggleSwitch()
        card.add_row("Spoken formatting commands", self.mode_commands)

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
        self.model_sub_label = None

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

        card_models = Card()
        card_models.add_title("Installed models")
        folder_wrap = QWidget()
        fw = QHBoxLayout(folder_wrap)
        fw.setContentsMargins(0, 0, 0, 0)
        self.models_dir = QLineEdit(cfg.models_dir)
        self.models_dir.setMinimumWidth(320)
        browse_models = QPushButton("Browse...")
        browse_models.clicked.connect(self._pick_models_dir)
        fw.addWidget(self.models_dir)
        fw.addWidget(browse_models)
        card_models.add_row(
            "Models folder",
            folder_wrap,
            sub="Whisper models are downloaded here. Existing cache folders are kept when you change this path.",
        )
        self.models_status_wrap = QWidget()
        self.models_status_layout = QVBoxLayout(self.models_status_wrap)
        self.models_status_layout.setContentsMargins(18, 8, 18, 14)
        self.models_status_layout.setSpacing(8)
        card_models.add_widget(self.models_status_wrap)
        v.addWidget(card_models)

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

        self.preset.currentIndexChanged.connect(self._load_selected_mode)
        self.mode_apps.editingFinished.connect(self._save_mode)
        self.mode_output.currentIndexChanged.connect(self._save_mode)
        self.mode_fillers.toggled_changed.connect(self._save_mode)
        self.mode_commands.toggled_changed.connect(self._save_mode)
        self.language.currentTextChanged.connect(self._save)
        self.voice_model.currentIndexChanged.connect(self._model_changed)
        self.compute_device.currentTextChanged.connect(self._save)
        self.compute_type.currentTextChanged.connect(self._save)
        self.streaming_toggle.toggled_changed.connect(self._save)
        self.models_dir.editingFinished.connect(self._save_models_dir)

        self._model_thread: QThread | None = None
        self._model_worker: _ModelWorker | None = None
        self._loading_mode = False
        self._load_selected_mode()
        self._refresh_model_status()

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
                    else "CPU (int8, ~5x real-time)"
                )
                return f"{m['subtitle']} • {device_note}"
        return ""

    # ── slots ─────────────────────────────────────────────────────────────────

    def _model_changed(self, _index: int) -> None:
        self._save()

    def _selected_mode(self) -> dict | None:
        mode_id = str(self.preset.currentData() or "")
        for mode in self.cfg.dictation_modes:
            if str(mode.get("id")) == mode_id:
                return mode
        return None

    def _rebuild_presets(self, selected_id: str) -> None:
        self.preset.blockSignals(True)
        try:
            self.preset.clear()
            for mode in self.cfg.dictation_modes:
                self.preset.addItem(
                    str(mode.get("name") or mode.get("id")),
                    str(mode.get("id")),
                )
            self.preset.setCurrentIndex(max(0, self.preset.findData(selected_id)))
        finally:
            self.preset.blockSignals(False)
        self._load_selected_mode()

    def _create_mode(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "New writing profile",
            "Profile name:",
        )
        name = name.strip()
        if not accepted or not name:
            return
        existing = {str(mode.get("id")) for mode in self.cfg.dictation_modes}
        base = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-") or "profile"
        mode_id = base
        suffix = 2
        while mode_id in existing:
            mode_id = f"{base}-{suffix}"
            suffix += 1
        self.cfg.dictation_modes.append(
            {
                "id": mode_id,
                "name": name,
                "description": "Custom writing profile.",
                "output_action": "default",
                "remove_fillers": True,
                "spoken_commands": True,
                "app_patterns": [],
            }
        )
        self.cfg.active_mode_id = mode_id
        self.cfg.save()
        self._rebuild_presets(mode_id)
        self.config_changed.emit()

    def _duplicate_mode(self) -> None:
        source = self._selected_mode()
        if source is None:
            return
        existing = {str(mode.get("id")) for mode in self.cfg.dictation_modes}
        base = f"{source.get('id', 'profile')}-copy"
        mode_id = base
        suffix = 2
        while mode_id in existing:
            mode_id = f"{base}-{suffix}"
            suffix += 1
        clone = {
            **source,
            "id": mode_id,
            "name": f"{source.get('name', 'Profile')} Copy",
            "app_patterns": list(source.get("app_patterns") or []),
        }
        self.cfg.dictation_modes.append(clone)
        self.cfg.active_mode_id = mode_id
        self.cfg.save()
        self._rebuild_presets(mode_id)
        self.config_changed.emit()

    def _delete_mode(self) -> None:
        selected = self._selected_mode()
        if selected is None:
            return
        if len(self.cfg.dictation_modes) <= 1:
            QMessageBox.information(self, "Keep one profile", "At least one writing profile is required.")
            return
        answer = QMessageBox.question(
            self,
            "Delete writing profile",
            f"Delete “{selected.get('name', selected.get('id'))}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        selected_id = str(selected.get("id"))
        self.cfg.dictation_modes = [
            mode for mode in self.cfg.dictation_modes if str(mode.get("id")) != selected_id
        ]
        next_id = str(self.cfg.dictation_modes[0].get("id") or "default")
        self.cfg.active_mode_id = next_id
        self.cfg.save()
        self._rebuild_presets(next_id)
        self.config_changed.emit()

    def _load_selected_mode(self, *_args) -> None:
        mode = self._selected_mode()
        if mode is None:
            return
        self._loading_mode = True
        try:
            self.cfg.active_mode_id = str(mode.get("id") or "default")
            self.mode_apps.setText(", ".join(str(v) for v in mode.get("app_patterns") or []))
            index = self.mode_output.findData(str(mode.get("output_action") or "default"))
            self.mode_output.setCurrentIndex(max(0, index))
            self.mode_fillers.setChecked(bool(mode.get("remove_fillers", True)))
            self.mode_commands.setChecked(bool(mode.get("spoken_commands", True)))
        finally:
            self._loading_mode = False
        self.cfg.save()
        self.config_changed.emit()

    def _save_mode(self, *_args) -> None:
        if self._loading_mode:
            return
        mode = self._selected_mode()
        if mode is None:
            return
        mode["app_patterns"] = [
            value.strip()
            for value in self.mode_apps.text().split(",")
            if value.strip()
        ]
        mode["output_action"] = str(self.mode_output.currentData() or "default")
        mode["remove_fillers"] = self.mode_fillers.isChecked()
        mode["spoken_commands"] = self.mode_commands.isChecked()
        self.cfg.save()
        self.config_changed.emit()

    def _save(self, *args):
        previous_model = self.cfg.model
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
        if self.cfg.model != previous_model:
            self._refresh_model_status()
        self.config_changed.emit()

    def _pick_models_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Select models folder", self.cfg.models_dir)
        if d:
            self.models_dir.setText(d)
            self._save_models_dir()

    def _save_models_dir(self) -> None:
        value = self.models_dir.text().strip()
        if value:
            self.cfg.models_dir = value
            self.cfg.save()
            self._refresh_model_status()
            self.config_changed.emit()

    def _refresh_model_status(self) -> None:
        while self.models_status_layout.count():
            item = self.models_status_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for status in list_model_status(self.cfg.models_dir, self.cfg.model):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            label = QLabel(self._status_label(status))
            label.setWordWrap(True)
            layout.addWidget(label, stretch=1)
            install = QPushButton("Installed" if status.installed else "Install")
            install.setEnabled(status.installable and not status.installed and not status.active and self._model_thread is None)
            install.clicked.connect(lambda _=False, key=status.key: self._run_model_action("install", key))
            layout.addWidget(install)
            uninstall = QPushButton("Uninstall")
            uninstall.setEnabled(status.installed and not status.active and self._model_thread is None)
            uninstall.clicked.connect(lambda _=False, key=status.key: self._run_model_action("uninstall", key))
            layout.addWidget(uninstall)
            self.models_status_layout.addWidget(row)
        self.models_status_layout.addStretch(1)

    @staticmethod
    def _status_label(status) -> str:
        if status.active and status.installed:
            state = "current + installed"
        elif status.active:
            state = "current (selected, install on first use)"
        else:
            state = "installed" if status.installed else "not installed"
        extra = f"\n{status.note}" if status.note else ""
        return f"{status.display_name} - {state}\n{status.cache_path}{extra}"

    def _run_model_action(self, action: str, key: str) -> None:
        if self._model_thread is not None:
            return
        self._model_thread = QThread(self)
        self._model_worker = _ModelWorker(action, key, self.cfg.models_dir, self.cfg.model)
        self._model_worker.moveToThread(self._model_thread)
        self._model_thread.started.connect(self._model_worker.run)
        self._model_worker.finished.connect(self._model_action_finished)
        self._model_worker.failed.connect(self._model_action_failed)
        self._model_worker.finished.connect(self._model_thread.quit)
        self._model_worker.failed.connect(self._model_thread.quit)
        self._model_thread.finished.connect(self._cleanup_model_thread)
        self._refresh_model_status()
        self._model_thread.start()

    def _model_action_finished(self) -> None:
        self._refresh_model_status()

    def _model_action_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Model operation failed", message)

    def _cleanup_model_thread(self) -> None:
        if self._model_worker is not None:
            self._model_worker.deleteLater()
        if self._model_thread is not None:
            self._model_thread.deleteLater()
        self._model_worker = None
        self._model_thread = None
        self._refresh_model_status()
