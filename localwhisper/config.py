from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .secret_store import SecretStore

CURRENT_SCHEMA_VERSION = 2


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "LocalWhisper"


def _local_appdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "LocalWhisper"


def _default_save_dir() -> Path:
    return Path.home() / "Documents" / "LocalWhisper"


def config_path() -> Path:
    return _appdata_dir() / "config.json"


def history_db_path() -> Path:
    return _appdata_dir() / "history.db"


def models_dir_path() -> Path:
    return _local_appdata_dir() / "models"


def secrets_path() -> Path:
    return _local_appdata_dir() / "secrets.json"


# Compatibility aliases for external scripts. Runtime code should call the
# functions above so test/environment overrides are honored after import.
CONFIG_PATH = config_path()
MODELS_DIR = models_dir_path()
HISTORY_DB = history_db_path()


def default_models_dir() -> str:
    return str(models_dir_path())


def default_dictation_modes() -> list[dict]:
    return [
        {
            "id": "default",
            "name": "Natural",
            "description": "Balanced dictation with clean punctuation.",
            "output_action": "insert",
            "remove_fillers": True,
            "spoken_commands": True,
            "app_patterns": [],
        },
        {
            "id": "verbatim",
            "name": "Verbatim",
            "description": "Faithful transcript without cleanup.",
            "output_action": "insert",
            "remove_fillers": False,
            "spoken_commands": False,
            "app_patterns": [],
        },
        {
            "id": "prompt",
            "name": "AI Prompt",
            "description": "Clean technical dictation for coding assistants.",
            "output_action": "insert",
            "remove_fillers": True,
            "spoken_commands": True,
            "app_patterns": ["codex", "cursor", "code", "chatgpt", "claude"],
        },
        {
            "id": "email",
            "name": "Email",
            "description": "Polished paragraphs for email clients.",
            "output_action": "insert",
            "remove_fillers": True,
            "spoken_commands": True,
            "app_patterns": ["outlook", "mail", "gmail"],
        },
        {
            "id": "chat",
            "name": "Chat",
            "description": "Concise dictation for messaging apps.",
            "output_action": "insert",
            "remove_fillers": True,
            "spoken_commands": True,
            "app_patterns": ["slack", "teams", "discord", "whatsapp", "telegram"],
        },
    ]


@dataclass
class Config:
    schema_version: int = CURRENT_SCHEMA_VERSION
    model: str = "whisper-turbo"  # whisper-turbo | parakeet-v3 | whisper-ultra
    language: str = "pt-BR"  # pt-BR | en | auto  (legacy values fall back to 'auto')
    streaming: bool = True  # True = live streaming injection, False = inject after stop
    hotkey_toggle: str = "ctrl+space"
    hotkey_cancel: str = "esc"
    hotkey_paste_last: str = "win+alt+space"
    input_device: str | None = None   # None = system default
    output_device: str | None = None  # None = system default
    save_dir: str = field(default_factory=lambda: str(_default_save_dir()))
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
    # Product behavior
    activation_mode: str = "toggle"  # toggle | push_to_talk
    overlay_mode: str = "compact"  # compact | full | hidden
    output_action: str = "insert"  # insert | insert_enter | clipboard | history
    active_mode_id: str = "default"
    dictation_modes: list[dict] = field(default_factory=default_dictation_modes)
    remove_filler_words: bool = True
    spoken_commands: bool = True
    smart_formatting: bool = True
    max_session_minutes: int = 20
    model_keep_warm_minutes: int = 15
    private_mode: bool = False
    history_retention_days: int = 30
    app_language: str = "pt-BR"
    onboarding_complete: bool = False
    # File-transcription feature
    hf_token: str = ""  # runtime-only; persisted encrypted with Windows DPAPI
    file_diarize: bool = True  # default: identify speakers when transcribing files
    file_last_dir: str = ""  # remembered "open file" directory

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        legacy_token = ""
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("config root must be an object")
                legacy_token = str(data.pop("hf_token", "") or "")
                cfg = cls()
                try:
                    cfg.schema_version = int(data.get("schema_version", 1) or 1)
                except (TypeError, ValueError):
                    cfg.schema_version = 1
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
                store = SecretStore(secrets_path())
                cfg.hf_token = store.get("hf_token") or legacy_token
                cfg._migrate_legacy()
                cfg._validate()
                if legacy_token or cfg.schema_version != data.get("schema_version"):
                    cfg.save()
                return cfg
            except Exception:
                pass
        cfg = cls()
        cfg.save()
        return cfg

    def _migrate_legacy(self) -> None:
        """Normalize values that came from older app versions."""
        previous_schema = self.schema_version
        # Language: only pt-BR and en are supported now. auto/pt-PT/es/fr/de/it
        # all get mapped to pt-BR (which keeps English terms via prompt bias).
        if self.language not in {"pt-BR", "en"}:
            self.language = "pt-BR"
        # compute_type: float32 was briefly an option but fails on Blackwell.
        if self.compute_type == "float32":
            self.compute_type = "float16"
        if not self.models_dir:
            self.models_dir = default_models_dir()
        defaults = default_dictation_modes()
        if not self.dictation_modes:
            self.dictation_modes = defaults
        elif previous_schema < CURRENT_SCHEMA_VERSION:
            known = {
                str(mode.get("id"))
                for mode in self.dictation_modes
                if isinstance(mode, dict)
            }
            self.dictation_modes.extend(
                mode for mode in defaults if str(mode.get("id")) not in known
            )
        if previous_schema < CURRENT_SCHEMA_VERSION:
            # Onboarding is for first installs. Existing users already have a
            # working microphone/hotkey setup and should not be interrupted by
            # an upgrade dialog.
            self.onboarding_complete = True
            # Older releases kept history indefinitely. Preserve that contract
            # during migration instead of silently pruning an existing archive.
            self.history_retention_days = 0
        self.schema_version = CURRENT_SCHEMA_VERSION
        if not self.vocabulary_replacements:
            vocab = {str(w).strip().lower() for w in self.vocabulary if str(w).strip()}
            if "claude" in vocab or "claude.md" in vocab:
                self.vocabulary_replacements = [
                    {"from": "cloud", "to": "CLAUDE"},
                    {"from": "cloude", "to": "CLAUDE"},
                    {"from": "claud", "to": "CLAUDE"},
                    {"from": "cloud.md", "to": "CLAUDE.md"},
                ]

    def _validate(self) -> None:
        if self.model not in {"whisper-turbo", "parakeet-v3", "whisper-ultra"}:
            self.model = "whisper-turbo"
        if self.compute_device not in {"auto", "cuda", "cpu"}:
            self.compute_device = "auto"
        if self.compute_type not in {"float16", "int8_float16", "int8"}:
            self.compute_type = "float16"
        if self.activation_mode not in {"toggle", "push_to_talk"}:
            self.activation_mode = "toggle"
        if self.overlay_mode not in {"compact", "full", "hidden"}:
            self.overlay_mode = "compact"
        if self.output_action not in {"insert", "insert_enter", "clipboard", "history"}:
            self.output_action = "insert"
        normalized_modes: list[dict] = []
        seen_ids: set[str] = set()
        values = self.dictation_modes if isinstance(self.dictation_modes, list) else []
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                continue
            mode_id = str(value.get("id") or f"profile-{index + 1}").strip()
            if not mode_id or mode_id in seen_ids:
                continue
            output_action = str(value.get("output_action") or "insert")
            if output_action not in {"insert", "insert_enter", "clipboard", "history"}:
                output_action = "insert"
            patterns = value.get("app_patterns")
            normalized_modes.append(
                {
                    **value,
                    "id": mode_id,
                    "name": str(value.get("name") or mode_id).strip() or mode_id,
                    "description": str(value.get("description") or ""),
                    "output_action": output_action,
                    "remove_fillers": bool(value.get("remove_fillers", True)),
                    "spoken_commands": bool(value.get("spoken_commands", True)),
                    "app_patterns": [
                        str(pattern).strip()
                        for pattern in (patterns if isinstance(patterns, list) else [])
                        if str(pattern).strip()
                    ],
                }
            )
            seen_ids.add(mode_id)
        if not normalized_modes:
            normalized_modes = default_dictation_modes()
        self.dictation_modes = normalized_modes
        if self.active_mode_id not in {str(mode["id"]) for mode in normalized_modes}:
            self.active_mode_id = str(normalized_modes[0]["id"])
        self.onboarding_complete = bool(self.onboarding_complete)
        try:
            self.sound_volume = min(1.0, max(0.0, float(self.sound_volume)))
        except (TypeError, ValueError):
            self.sound_volume = 0.8
        try:
            self.max_session_minutes = min(120, max(1, int(self.max_session_minutes)))
        except (TypeError, ValueError):
            self.max_session_minutes = 20
        try:
            self.model_keep_warm_minutes = min(240, max(0, int(self.model_keep_warm_minutes)))
        except (TypeError, ValueError):
            self.model_keep_warm_minutes = 15
        try:
            self.history_retention_days = min(3650, max(0, int(self.history_retention_days)))
        except (TypeError, ValueError):
            self.history_retention_days = 30

    def save(self) -> None:
        self._validate()
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                backup = path.with_suffix(".json.bak")
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        payload = asdict(self)
        token = str(payload.pop("hf_token", "") or "")
        SecretStore(secrets_path()).set("hf_token", token)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temp, path)
