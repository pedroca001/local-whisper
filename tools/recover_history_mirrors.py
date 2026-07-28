"""Audit or rebuild missing daily transcript mirrors from history.db."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("output_dir")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    database = Path(args.database).resolve()
    output_dir = Path(args.output_dir).resolve()
    uri = f"{database.as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT started_at,model,text,target_app FROM transcriptions "
            "ORDER BY started_at,id"
        ).fetchall()

    by_day: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_day[str(row["started_at"])[:10]].append(row)
    missing = [day for day in sorted(by_day) if not (output_dir / f"{day}.txt").exists()]
    print(
        json.dumps(
            {
                "database": str(database),
                "output_dir": str(output_dir),
                "database_rows": len(rows),
                "database_days": len(by_day),
                "missing_days": missing,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.apply:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    for day in missing:
        chunks = []
        for row in by_day[day]:
            chunks.append(
                f"\n[{row['started_at']}] ({row['model']}) -> "
                f"{row['target_app'] or 'overlay'}\n{str(row['text']).strip()}\n"
            )
        destination = output_dir / f"{day}.txt"
        destination.write_text("".join(chunks), encoding="utf-8")
        print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
