from __future__ import annotations

from localwhisper.doctor import run_doctor


def test_doctor_does_not_create_user_data(monkeypatch, tmp_path):
    roaming = tmp_path / "roaming"
    local = tmp_path / "local"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    result = run_doctor()

    assert result["ok"] is True
    assert not (roaming / "LocalWhisper").exists()
    assert not (local / "LocalWhisper").exists()
