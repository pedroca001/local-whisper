from __future__ import annotations

from localwhisper import diagnostics
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


def test_support_values_redact_user_home_and_nested_errors(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\PrivatePerson")
    report = {
        "executable": r"C:\Users\PrivatePerson\AppData\Local\Python\python.exe",
        "checks": {
            "history": {
                "error": (
                    r"cannot open C:\Users\PrivatePerson\AppData\Roaming"
                    r"\LocalWhisper\history.db"
                )
            }
        },
    }

    redacted = diagnostics.redact_support_value(report)

    assert "PrivatePerson" not in str(redacted)
    assert redacted["executable"].startswith("%USERPROFILE%")
