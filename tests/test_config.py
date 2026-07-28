from __future__ import annotations

import json
import sys

import pytest

from localwhisper.config import (
    CURRENT_SCHEMA_VERSION,
    Config,
    config_path,
    secrets_path,
)


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))


def test_config_save_is_atomic_and_validated(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = Config(
        sound_volume=9,
        max_session_minutes=999,
        history_retention_days=-1,
        output_action="invalid",
    )
    cfg.save()

    data = json.loads(config_path().read_text(encoding="utf-8"))
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION
    assert data["sound_volume"] == 1.0
    assert data["max_session_minutes"] == 120
    assert data["history_retention_days"] == 0
    assert data["output_action"] == "insert"
    assert not config_path().with_suffix(".json.tmp").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_huggingface_token_is_not_written_to_plaintext_config(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    token = "hf_localwhisper_test_secret"
    cfg = Config(hf_token=token)
    cfg.save()

    assert token not in config_path().read_text(encoding="utf-8")
    assert token not in secrets_path().read_text(encoding="utf-8")
    assert Config.load().hf_token == token


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_legacy_plaintext_token_is_migrated(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "hf_token": "hf_legacy_secret"}),
        encoding="utf-8",
    )

    cfg = Config.load()
    assert cfg.hf_token == "hf_legacy_secret"
    assert "hf_legacy_secret" not in path.read_text(encoding="utf-8")
    assert cfg.schema_version == CURRENT_SCHEMA_VERSION


def test_invalid_writing_profiles_are_normalized(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cfg = Config()
    cfg.dictation_modes = [
        "invalid",
        {
            "id": "custom",
            "name": "",
            "output_action": "dangerous",
            "app_patterns": "not-a-list",
        },
        {"id": "custom", "name": "duplicate"},
    ]
    cfg.active_mode_id = "missing"
    cfg.save()

    loaded = Config.load()
    assert len(loaded.dictation_modes) == 1
    assert loaded.dictation_modes[0]["id"] == "custom"
    assert loaded.dictation_modes[0]["output_action"] == "insert"
    assert loaded.dictation_modes[0]["app_patterns"] == []
    assert loaded.active_mode_id == "custom"
