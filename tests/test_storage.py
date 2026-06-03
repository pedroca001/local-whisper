import os
import tempfile
import uuid

# Override config DB path before import
tmp = tempfile.mkdtemp(prefix="lw_test_")
os.environ["APPDATA"] = tmp
os.environ["LOCALAPPDATA"] = tmp

from localwhisper import storage  # noqa: E402


def test_add_and_list():
    storage.add_transcription(
        text="ola mundo, acao nao e coracao",
        duration_ms=1234,
        model="whisper-turbo",
        target_app="notepad.exe",
        injected=True,
        save_dir=tmp,
    )
    rows = storage.list_recent(7)
    assert len(rows) >= 1
    assert "acao" in rows[0]["text"]


def test_search():
    token = f"xyzzy-{uuid.uuid4().hex}"
    storage.add_transcription(
        text=f"texto unico {token} presente",
        duration_ms=500,
        model="whisper-turbo",
        save_dir=tmp,
    )
    rows = storage.search(token, days=7)
    assert len(rows) == 1
    assert token in rows[0]["text"]
