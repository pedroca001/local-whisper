"""Exercise History virtualization and stale-query handling with synthetic data."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from localwhisper.config import Config
from localwhisper.ui.pages import history as history_module


def _row(row_id: int, text: str, *, favorite: bool = False) -> dict:
    return {
        "id": row_id,
        "started_at": "2026-01-01T12:00:00",
        "duration_ms": 1200,
        "model": "whisper-turbo",
        "target_app": "smoke.exe",
        "text": text,
        "favorite": 1 if favorite else 0,
    }


def main() -> int:
    rows = [_row(index, f"synthetic history row {index}") for index in range(1, 201)]
    revision = {"value": 1}
    search_calls = {"count": 0}

    def list_recent(*, days: int, favorites_only: bool = False) -> list[dict]:
        time.sleep(0.15)
        return [row for row in rows if not favorites_only or row["favorite"]]

    def search(query: str, *, days: int) -> list[dict]:
        search_calls["count"] += 1
        captured_revision = revision["value"]
        time.sleep(0.08)
        if query != "latest":
            return []
        return [
            _row(
                999 + captured_revision,
                f"latest filter result v{captured_revision}",
                favorite=True,
            )
        ]

    def stats(days: int) -> dict:
        return {
            "sessions": len(rows),
            "words": 800,
            "duration_minutes": 4.0,
            "words_per_minute": 200.0,
        }

    history_module.storage.list_recent = list_recent
    history_module.storage.search = search
    history_module.storage.stats = stats

    app = QApplication.instance() or QApplication([])
    cfg = Config()
    cfg.history_retention_days = 0
    page = history_module.HistoryPage(cfg)
    page.refresh_async()
    assert page._thread is None
    assert page._stale
    started = time.monotonic()
    page.show()
    QTimer.singleShot(20, lambda: page.search.setText("latest"))
    phase = {"value": "initial"}

    def finish_when_ready() -> None:
        if page._thread is not None or page._table_model.rowCount() != 1:
            if time.monotonic() - started > 5:
                print("history-ui-timeout", file=sys.stderr)
                app.exit(2)
                return
            QTimer.singleShot(20, finish_when_ready)
            return

        # Model resets invalidate existing QModelIndex objects, so always
        # resolve the current cell after an asynchronous refresh completes.
        index = page._table_model.index(0, 5)
        if phase["value"] == "initial":
            assert page._table_model.data(index) == "latest filter result v1"
            phase["value"] = "same-filter-refresh"
            page._invalidate_and_refresh()

            def invalidate_same_filter() -> None:
                revision["value"] = 2
                page._invalidate_and_refresh()

            QTimer.singleShot(20, invalidate_same_filter)
            QTimer.singleShot(20, finish_when_ready)
            return

        if page._table_model.data(index) != "latest filter result v2":
            if time.monotonic() - started > 5:
                current = page._table_model.data(page._table_model.index(0, 5))
                print(
                    "history-ui-stale-result "
                    f"current={current!r} calls={search_calls['count']} "
                    f"generation={page._generation} stale={page._stale}",
                    file=sys.stderr,
                )
                app.exit(3)
                return
            QTimer.singleShot(20, finish_when_ready)
            return

        assert search_calls["count"] >= 3
        assert page._last_loaded_request == ("latest", 3650, False)
        assert page.stats_label.text().startswith("200 sessions")
        elapsed_ms = round((time.monotonic() - started) * 1000)
        print(f"history-ui-ok rows=200 final_rows=1 elapsed_ms={elapsed_ms}")
        page.close()
        app.exit(0)

    QTimer.singleShot(20, finish_when_ready)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
