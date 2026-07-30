from __future__ import annotations

import re
from pathlib import Path

from localwhisper import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_are_consistent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject)
    installer = (ROOT / "installer.iss").read_text(encoding="utf-8")
    installer_match = re.search(r'#define AppVersion\s+"([^"]+)"', installer)

    assert project_match is not None
    assert installer_match is not None
    project_version = project_match.group(1)
    assert project_version == __version__
    assert installer_match.group(1) == project_version
    assert f"## {project_version}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_install_check_probes_editable_source_outside_the_checkout() -> None:
    installer = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "Push-Location ([System.IO.Path]::GetTempPath())" in installer
    assert "finally {" in installer
    assert "Pop-Location" in installer
