from pathlib import Path

from localwhisper.model_manager import list_model_status, uninstall_model


def test_model_status_reports_active_and_cache_path(tmp_path):
    statuses = list_model_status(tmp_path, "whisper-turbo")
    turbo = next(s for s in statuses if s.key == "whisper-turbo")
    assert turbo.active
    assert turbo.cache_kind == "huggingface"
    assert str(tmp_path) in turbo.cache_path


def test_uninstall_refuses_active_model(tmp_path):
    try:
        uninstall_model("whisper-turbo", tmp_path, "whisper-turbo")
    except RuntimeError as exc:
        assert "active model" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_uninstall_removes_non_active_hf_cache(tmp_path):
    cache = Path(tmp_path) / "models--Systran--faster-whisper-large-v3"
    cache.mkdir()
    (cache / "marker").write_text("x", encoding="utf-8")
    uninstall_model("whisper-ultra", tmp_path, "whisper-turbo")
    assert not cache.exists()
