from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta

from localwhisper import storage
from localwhisper.config import history_db_path


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return tmp_path / "transcripts"


def test_add_and_list(monkeypatch, tmp_path):
    save_dir = _isolate(monkeypatch, tmp_path)
    storage.add_transcription(
        text="ola mundo, acao nao e coracao",
        duration_ms=1234,
        model="whisper-turbo",
        target_app="notepad.exe",
        injected=True,
        save_dir=str(save_dir),
        mode="default",
    )
    rows = storage.list_recent(7)
    assert len(rows) == 1
    assert "acao" in rows[0]["text"]
    assert rows[0]["word_count"] == 6
    assert rows[0]["mode"] == "default"


def test_search(monkeypatch, tmp_path):
    save_dir = _isolate(monkeypatch, tmp_path)
    token = f"xyzzy-{uuid.uuid4().hex}"
    storage.add_transcription(
        text=f"texto unico {token} presente",
        duration_ms=500,
        model="whisper-turbo",
        save_dir=str(save_dir),
    )
    rows = storage.search(token, days=7)
    assert len(rows) == 1
    assert token in rows[0]["text"]


def test_stats_and_favorites(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    row_id = storage.add_transcription(
        text="um dois tres quatro",
        duration_ms=2000,
        model="whisper-turbo",
    )
    storage.set_favorite(row_id, True)

    result = storage.stats(30)
    assert result["sessions"] == 1
    assert result["words"] == 4
    assert result["words_per_minute"] == 120.0
    assert storage.list_recent(7, favorites_only=True)[0]["id"] == row_id


def test_cleanup_preserves_favorites(monkeypatch, tmp_path):
    save_dir = _isolate(monkeypatch, tmp_path)
    old = (datetime.now() - timedelta(days=90)).isoformat(timespec="seconds")
    save_dir.mkdir(parents=True)
    old_dump = save_dir / f"{old[:10]}.txt"
    old_dump.write_text("favorite mirror", encoding="utf-8")
    orphan_dump = save_dir / "2020-01-01.txt"
    orphan_dump.write_text("not represented by this database", encoding="utf-8")
    with storage._connect() as conn:
        conn.execute(
            "INSERT INTO transcriptions("
            "started_at,duration_ms,model,text,injected,mode,favorite,word_count"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (old, 1000, "whisper-turbo", "ordinary old row", 0, "default", 0, 3),
        )
        conn.execute(
            "INSERT INTO transcriptions("
            "started_at,duration_ms,model,text,injected,mode,favorite,word_count"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (old, 1000, "whisper-turbo", "favorite old row", 0, "default", 1, 3),
        )

    result = storage.cleanup_old(30, save_dir=str(save_dir))
    assert result["rows_deleted"] == 1
    assert old_dump.exists()
    assert orphan_dump.exists()
    with sqlite3.connect(str(history_db_path())) as conn:
        rows = conn.execute("SELECT text FROM transcriptions").fetchall()
    assert rows == [("favorite old row",)]


def test_schema_migrates_existing_database(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    path = history_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                model TEXT NOT NULL,
                text TEXT NOT NULL,
                target_app TEXT,
                target_window_title TEXT,
                injected INTEGER NOT NULL DEFAULT 0
            );
            """
        )
    with storage._connect() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transcriptions)")}
    assert {"mode", "favorite", "word_count"} <= columns
