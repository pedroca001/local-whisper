"""SQLite-backed transcription history + .txt mirror dump."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import history_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    model TEXT NOT NULL,
    text TEXT NOT NULL,
    target_app TEXT,
    target_window_title TEXT,
    injected INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'default',
    favorite INTEGER NOT NULL DEFAULT 0,
    word_count INTEGER NOT NULL DEFAULT 0
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(transcriptions)")}
    migrations = {
        "mode": "ALTER TABLE transcriptions ADD COLUMN mode TEXT NOT NULL DEFAULT 'default'",
        "favorite": "ALTER TABLE transcriptions ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0",
        "word_count": "ALTER TABLE transcriptions ADD COLUMN word_count INTEGER NOT NULL DEFAULT 0",
    }
    for name, statement in migrations.items():
        if name not in columns:
            conn.execute(statement)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_started_at "
        "ON transcriptions(started_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_favorite "
        "ON transcriptions(favorite, started_at DESC)"
    )
    conn.execute(
        "UPDATE transcriptions SET word_count = "
        "CASE WHEN length(trim(text)) = 0 THEN 0 "
        "ELSE length(trim(text)) - length(replace(trim(text), ' ', '')) + 1 END "
        "WHERE word_count = 0"
    )


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else history_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def add_transcription(
    text: str,
    duration_ms: int,
    model: str,
    target_app: Optional[str] = None,
    target_window_title: Optional[str] = None,
    injected: bool = False,
    save_dir: Optional[str] = None,
    mode: str = "default",
) -> int:
    if not text.strip():
        return 0
    started_at = datetime.now().isoformat(timespec="seconds")
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO transcriptions("
            "started_at,duration_ms,model,text,target_app,target_window_title,injected,mode,word_count"
            ") VALUES (?,?,?,?,?,?,?,?,?)",
            (
                started_at,
                duration_ms,
                model,
                text,
                target_app,
                target_window_title,
                1 if injected else 0,
                mode or "default",
                len(text.split()),
            ),
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


def list_recent(days: int = 7, limit: int = 200, favorites_only: bool = False) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=max(0, days))).isoformat(timespec="seconds")
    favorite_clause = " AND favorite=1" if favorites_only else ""
    with _connect() as c:
        rows = c.execute(
            f"SELECT * FROM transcriptions WHERE started_at >= ?{favorite_clause} "
            "ORDER BY started_at DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def search(query: str, days: int = 7, limit: int = 200) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM transcriptions WHERE started_at >= ? AND text LIKE ? "
            "ORDER BY started_at DESC LIMIT ?",
            (cutoff, f"%{query}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_transcription(row_id: int) -> None:
    with _connect() as c:
        c.execute("DELETE FROM transcriptions WHERE id=?", (row_id,))


def set_favorite(row_id: int, favorite: bool) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE transcriptions SET favorite=? WHERE id=?",
            (1 if favorite else 0, row_id),
        )


def cleanup_old(days: int, *, save_dir: str | None = None) -> dict:
    """Delete non-favorite history older than ``days``.

    ``days=0`` disables automatic cleanup.
    """
    if days <= 0:
        return {"rows_deleted": 0, "files_deleted": 0}
    cutoff_dt = datetime.now() - timedelta(days=days)
    cutoff = cutoff_dt.isoformat(timespec="seconds")
    with _connect() as c:
        managed_days = {
            str(row[0])
            for row in c.execute(
                "SELECT DISTINCT substr(started_at,1,10) FROM transcriptions "
                "WHERE started_at < ?",
                (cutoff,),
            ).fetchall()
        }
        favorite_days = {
            str(row[0])
            for row in c.execute(
                "SELECT DISTINCT substr(started_at,1,10) FROM transcriptions "
                "WHERE started_at < ? AND favorite=1",
                (cutoff,),
            ).fetchall()
        }
        rows_deleted = c.execute(
            "SELECT COUNT(*) FROM transcriptions WHERE started_at < ? AND favorite=0",
            (cutoff,),
        ).fetchone()[0]
        c.execute(
            "DELETE FROM transcriptions WHERE started_at < ? AND favorite=0",
            (cutoff,),
        )
    files_deleted = 0
    if save_dir:
        folder = Path(save_dir)
        if folder.is_dir():
            for path in folder.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].txt"):
                try:
                    file_day = datetime.strptime(path.stem, "%Y-%m-%d")
                    if (
                        file_day < cutoff_dt
                        and path.stem in managed_days
                        and path.stem not in favorite_days
                    ):
                        path.unlink()
                        files_deleted += 1
                except (OSError, ValueError):
                    continue
    return {"rows_deleted": int(rows_deleted), "files_deleted": files_deleted}


def stats(days: int = 30) -> dict:
    cutoff = (datetime.now() - timedelta(days=max(0, days))).isoformat(timespec="seconds")
    with _connect() as c:
        row = c.execute(
            "SELECT COUNT(*) AS sessions, COALESCE(SUM(word_count),0) AS words, "
            "COALESCE(SUM(duration_ms),0) AS duration_ms "
            "FROM transcriptions WHERE started_at >= ?",
            (cutoff,),
        ).fetchone()
    duration_minutes = float(row["duration_ms"] or 0) / 60000.0
    words = int(row["words"] or 0)
    return {
        "days": days,
        "sessions": int(row["sessions"] or 0),
        "words": words,
        "duration_minutes": round(duration_minutes, 2),
        "words_per_minute": round(words / duration_minutes, 1) if duration_minutes else 0.0,
    }


def export_history(days: int = 30, format: str = "markdown") -> str:
    rows = list_recent(days=max(0, days), limit=100000)
    if format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)
    chunks = ["# LocalWhisper history", ""]
    for row in reversed(rows):
        favorite = " star" if row.get("favorite") else ""
        chunks.extend(
            [
                f"## {row['started_at']} - {row.get('model', '')}{favorite}",
                "",
                str(row.get("text") or "").strip(),
                "",
            ]
        )
    return "\n".join(chunks).rstrip() + "\n"


def clear_all(save_dir: str | None = None) -> dict:
    """Wipe the SQLite history and (if `save_dir` is given) the daily .txt files.

    Returns a summary dict {rows_deleted, files_deleted, save_dir}.
    """
    with _connect() as c:
        rows_deleted = c.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0]
        c.execute("DELETE FROM transcriptions")
        c.execute("DELETE FROM sqlite_sequence WHERE name='transcriptions'")
    # VACUUM must run outside an explicit transaction
    conn = sqlite3.connect(str(history_db_path()))
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
