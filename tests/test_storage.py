import os
import tempfile
from pathlib import Path

# Override config DB path before import
tmp = tempfile.mkdtemp(prefix="lw_test_")
os.environ["APPDATA"] = tmp
os.environ["LOCALAPPDATA"] = tmp

from localwhisper import storage  # noqa: E402


def test_add_and_list():
    storage.add_transcription(
        text="olá mundo, ação não é coração",
        duration_ms=1234,
        model="whisper-turbo",
        target_app="notepad.exe",
        injected=True,
        save_dir=tmp,
    )
    rows = storage.list_recent(7)
    assert len(rows) >= 1
    assert "ação" in rows[0]["text"]


def test_search():
    storage.add_transcription(
        text="texto único xyzzy presente",
        duration_ms=500,
        model="whisper-turbo",
        save_dir=tmp,
    )
    rows = storage.search("xyzzy", days=7)
    assert len(rows) == 1
    assert "xyzzy" in rows[0]["text"]
