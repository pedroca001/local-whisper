from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    p = Path(base) / "LocalWhisper"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _local_appdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    p = Path(base) / "LocalWhisper"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _default_save_dir() -> Path:
    p = Path.home() / "Documents" / "LocalWhisper"
    p.mkdir(parents=True, exist_ok=True)
    return p


CONFIG_PATH = _appdata_dir() / "config.json"
MODELS_DIR = _local_appdata_dir() / "models"
HISTORY_DB = _appdata_dir() / "history.db"


def default_models_dir() -> str:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return str(MODELS_DIR)


@dataclass
class Config:
    model: str = "whisper-turbo"  # whisper-turbo | parakeet-v3 | whisper-ultra
    language: str = "pt-BR"  # pt-BR | en | auto  (legacy values fall back to 'auto')
    streaming: bool = True  # True = live streaming injection, False = inject after stop
    hotkey_toggle: str = "ctrl+space"
    hotkey_cancel: str = "esc"
    hotkey_paste_last: str = "win+alt+space"
    input_device: str | None = None   # None = system default
    output_device: str | None = None  # None = system default
    save_dir: str = str(_default_save_dir())
    auto_mic_boost: bool = True
    silence_removal: bool = False
    sound_effects: bool = True
    sound_volume: float = 0.8
    auto_launch: bool = False
    compute_device: str = "auto"  # auto | cuda | cpu
    compute_type: str = "float16"  # float32 | float16 | int8_float16 | int8
    vocabulary: list[str] = field(default_factory=list)
    vocabulary_replacements: list[dict] = field(default_factory=list)
    models_dir: str = field(default_factory=default_models_dir)
    # File-transcription feature
    hf_token: str = ""  # HuggingFace token for pyannote speaker diarization
    file_diarize: bool = True  # default: identify speakers when transcribing files
    file_last_dir: str = ""  # remembered "open file" directory

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                cfg = cls()
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                cfg._migrate_legacy()
                return cfg
            except Exception:
                pass
        cfg = cls()
        cfg.save()
        return cfg

    def _migrate_legacy(self) -> None:
        """Normalize values that came from older app versions."""
        # Language: only pt-BR and en are supported now. auto/pt-PT/es/fr/de/it
        # all get mapped to pt-BR (which keeps English terms via prompt bias).
        if self.language not in {"pt-BR", "en"}:
            self.language = "pt-BR"
        # compute_type: float32 was briefly an option but fails on Blackwell.
        if self.compute_type == "float32":
            self.compute_type = "float16"
        if not self.models_dir:
            self.models_dir = default_models_dir()
        if not self.vocabulary_replacements:
            vocab = {str(w).strip().lower() for w in self.vocabulary if str(w).strip()}
            if "claude" in vocab or "claude.md" in vocab:
                self.vocabulary_replacements = [
                    {"from": "cloud", "to": "CLAUDE"},
                    {"from": "cloude", "to": "CLAUDE"},
                    {"from": "claud", "to": "CLAUDE"},
                    {"from": "cloud.md", "to": "CLAUDE.md"},
                ]

    def save(self) -> None:
        if CONFIG_PATH.exists():
            try:
                backup = CONFIG_PATH.with_suffix(".json.bak")
                backup.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
