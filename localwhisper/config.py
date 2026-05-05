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


@dataclass
class Config:
    model: str = "whisper-turbo"  # whisper-turbo | parakeet-v3 | whisper-ultra
    language: str = "pt-BR"  # pt-BR | pt-PT | en | es | fr | de | it | auto
    streaming: bool = True  # True = live streaming injection, False = inject after stop
    hotkey_toggle: str = "ctrl+space"
    hotkey_cancel: str = "esc"
    input_device: str | None = None   # None = system default
    output_device: str | None = None  # None = system default
    save_dir: str = str(_default_save_dir())
    auto_mic_boost: bool = True
    silence_removal: bool = False
    sound_effects: bool = True
    sound_volume: float = 0.8
    auto_launch: bool = False
    compute_type: str = "float16"  # float16 | int8_float16 | int8
    vocabulary: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                cfg = cls()
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                return cfg
            except Exception:
                pass
        cfg = cls()
        cfg.save()
        return cfg

    def save(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
