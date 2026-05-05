"""SQLite-backed transcription history + .txt mirror dump."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import HISTORY_DB


SCHEMA = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    model TEXT NOT NULL,
    text TEXT NOT NULL,
    target_app TEXT,
    target_window_title TEXT,
    injected INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_started_at ON transcriptions(started_at DESC);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def add_transcription(
    text: str,
    duration_ms: int,
    model: str,
    target_app: Optional[str] = None,
    target_window_title: Optional[str] = None,
    injected: bool = False,
    save_dir: Optional[str] = None,
) -> int:
    if not text.strip():
        return 0
    started_at = datetime.now().isoformat(timespec="seconds")
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO transcriptions(started_at,duration_ms,model,text,target_app,target_window_title,injected) "
            "VALUES (?,?,?,?,?,?,?)",
            (started_at, duration_ms, model, text, target_app, target_window_title, 1 if injected else 0),
        )
        row_id = cur.lastrowid

    if save_dir:
        try:
            _dump_txt(text, started_at, model, target_app, save_dir)
        except Exception:
            pass

    return row_id


def _dump_txt(text: str, started_at: str, model: str, target_app: Optional[str], save_dir: str) -> None:
    p = Path(save_dir)
    p.mkdir(parents=True, exist_ok=True)
    day = started_at.split("T")[0]
    f = p / f"{day}.txt"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n[{started_at}] ({model}) -> {target_app or 'overlay'}\n{text.strip()}\n")


def list_recent(days: int = 7) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM transcriptions WHERE started_at >= ? ORDER BY started_at DESC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def search(query: str, days: int = 7) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM transcriptions WHERE started_at >= ? AND text LIKE ? ORDER BY started_at DESC",
            (cutoff, f"%{query}%"),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_transcription(row_id: int) -> None:
    with _connect() as c:
        c.execute("DELETE FROM transcriptions WHERE id=?", (row_id,))


def clear_all(save_dir: str | None = None) -> dict:
    """Wipe the SQLite history and (if `save_dir` is given) the daily .txt files.

    Returns a summary dict {rows_deleted, files_deleted, save_dir}.
    """
    with _connect() as c:
        rows_deleted = c.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0]
        c.execute("DELETE FROM transcriptions")
        c.execute("DELETE FROM sqlite_sequence WHERE name='transcriptions'")
    # VACUUM must run outside an explicit transaction
    conn = sqlite3.connect(str(HISTORY_DB))
    try:
        conn.isolation_level = None
        conn.execute("VACUUM")
    finally:
        conn.close()

    files_deleted = 0
    if save_dir:
        p = Path(save_dir)
        if p.is_dir():
            # Daily dumps follow the YYYY-MM-DD.txt pattern (10 chars + .txt)
            for f in p.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].txt"):
                try:
                    f.unlink()
                    files_deleted += 1
                except Exception:
                    pass

    return {
        "rows_deleted": int(rows_deleted),
        "files_deleted": files_deleted,
        "save_dir": save_dir,
    }
