from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ... import storage
from ...config import Config


class _HistoryLoader(QObject):
    """Runs the SQLite query off the UI thread and emits the rows."""

    loaded = Signal(list, str, dict)  # rows, original_query, stats

    def run(self, query: str, days: int, favorites_only: bool) -> None:
        try:
            rows = (
                storage.search(query, days=days)
                if query
                else storage.list_recent(days=days, favorites_only=favorites_only)
            )
            if favorites_only and query:
                rows = [row for row in rows if row.get("favorite")]
            summary = storage.stats(days)
        except Exception:
            rows = []
            summary = {}
        self.loaded.emit(rows, query, summary)


class HistoryPage(QWidget):
    def __init__(self, cfg: Config | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg or Config.load()

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(12)

        title = QLabel("History")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)
        sub = QLabel("Search, favorite, export and recover your local dictations.")
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        v.addWidget(sub)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._on_search_changed)
        bar.addWidget(self.search)
        self.favorites_only = QCheckBox("Favorites")
        self.favorites_only.toggled.connect(lambda _on: self._invalidate_and_refresh())
        bar.addWidget(self.favorites_only)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_async)
        bar.addWidget(refresh)
        v.addLayout(bar)

        self.status_label = QLabel("Loading…")
        self.status_label.setStyleSheet("color: #888; padding: 4px 0;")
        v.addWidget(self.status_label)
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #555; padding: 0 0 4px 0;")
        v.addWidget(self.stats_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Date", "Duration", "Model", "App", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellClicked.connect(self._show_detail)
        v.addWidget(self.table, stretch=1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)
        self.detail.setPlaceholderText("Select a transcription to view full text.")
        self.detail.setStyleSheet("QTextEdit { background: #ffffff; color: #1d1d1f; }")
        v.addWidget(self.detail)

        actions = QHBoxLayout()
        clear = QPushButton("Clear history…")
        clear.clicked.connect(self._clear_all)
        clear.setStyleSheet("color: #ff3b30;")
        actions.addWidget(clear)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete_selected)
        actions.addWidget(delete)
        favorite = QPushButton("Toggle favorite")
        favorite.clicked.connect(self._toggle_favorite)
        actions.addWidget(favorite)
        actions.addStretch(1)
        export = QPushButton("Export…")
        export.clicked.connect(self._export)
        actions.addWidget(export)
        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy)
        actions.addWidget(copy)
        v.addLayout(actions)

        self._rows: list[dict] = []
        self._thread: QThread | None = None
        self._loader: _HistoryLoader | None = None
        self._pending_query: str | None = None
        self._last_loaded_at: float = 0.0
        self._last_loaded_query: str | None = None

        # Debounce search typing so we don't spawn a thread per keystroke.
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(180)
        self._search_debounce.timeout.connect(self.refresh_async)

        self.refresh_async()

    # ── data flow ────────────────────────────────────────────────────────────

    def _on_search_changed(self, _text: str) -> None:
        self._search_debounce.start()

    def _invalidate_and_refresh(self) -> None:
        self._last_loaded_at = 0.0
        self.refresh_async()

    def refresh_async(self):
        query = self.search.text().strip()
        # 2-second cache: if same query was just loaded, skip.
        if (
            self._last_loaded_query == query
            and (time.monotonic() - self._last_loaded_at) < 2.0
            and self._thread is None
        ):
            return
        if self._thread is not None and self._thread.isRunning():
            # Worker busy — remember the latest query and re-run when it finishes.
            self._pending_query = query
            return
        self._spawn_loader(query)

    def _spawn_loader(self, query: str) -> None:
        self.status_label.setText("Loading…")
        self.status_label.setVisible(True)

        thread = QThread(self)
        loader = _HistoryLoader()
        loader.moveToThread(thread)
        loader.loaded.connect(self._on_loaded)
        days = self.cfg.history_retention_days or 3650
        favorites_only = self.favorites_only.isChecked()
        thread.started.connect(lambda: loader.run(query, days, favorites_only))
        thread.finished.connect(loader.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._loader = loader
        thread.start()

    def _on_loaded(self, rows: list, query: str, summary: dict) -> None:
        self._rows = rows
        self._apply_rows(rows)
        if summary:
            self.stats_label.setText(
                f"{summary['sessions']} sessions · {summary['words']} words · "
                f"{summary['duration_minutes']:.1f} min · {summary['words_per_minute']:.0f} wpm"
            )
        self._last_loaded_at = time.monotonic()
        self._last_loaded_query = query

        if self._thread is not None:
            self._thread.quit()
            self._thread = None
            self._loader = None

        # If a newer query came in while loading, kick off another pass.
        pending = self._pending_query
        self._pending_query = None
        current_query = self.search.text().strip()
        if pending is not None and pending != query:
            self._spawn_loader(pending)
        elif current_query != query:
            self._spawn_loader(current_query)

    def _apply_rows(self, rows: list[dict]) -> None:
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            for i, r in enumerate(rows):
                ts = r["started_at"].replace("T", " ")
                self.table.setItem(i, 0, QTableWidgetItem("★" if r.get("favorite") else ""))
                self.table.setItem(i, 1, QTableWidgetItem(ts))
                self.table.setItem(i, 2, QTableWidgetItem(f"{r['duration_ms']/1000:.1f}s"))
                self.table.setItem(i, 3, QTableWidgetItem(r.get("model", "")))
                self.table.setItem(i, 4, QTableWidgetItem(r.get("target_app") or "—"))
                text = (r["text"] or "").replace("\n", " ")
                if len(text) > 120:
                    text = text[:120] + "…"
                self.table.setItem(i, 5, QTableWidgetItem(text))
        finally:
            self.table.setUpdatesEnabled(True)

        if rows:
            self.status_label.setVisible(False)
        else:
            self.status_label.setText("No matching transcriptions.")
            self.status_label.setVisible(True)

    # ── interactions ─────────────────────────────────────────────────────────

    def _show_detail(self, row: int, _col: int):
        if 0 <= row < len(self._rows):
            self.detail.setPlainText(self._rows[row]["text"])

    def _copy(self):
        if self.detail.toPlainText():
            QGuiApplication.clipboard().setText(self.detail.toPlainText())

    def _selected_row(self) -> dict | None:
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _toggle_favorite(self):
        row = self._selected_row()
        if not row:
            return
        storage.set_favorite(int(row["id"]), not bool(row.get("favorite")))
        self._invalidate_and_refresh()

    def _delete_selected(self):
        row = self._selected_row()
        if not row:
            return
        storage.delete_transcription(int(row["id"]))
        self.detail.clear()
        self._invalidate_and_refresh()

    def _export(self):
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export LocalWhisper history",
            "localwhisper-history.md",
            "Markdown (*.md);;JSON (*.json)",
        )
        if not path:
            return
        format_name = "json" if path.lower().endswith(".json") or "JSON" in selected else "markdown"
        days = self.cfg.history_retention_days or 3650
        from pathlib import Path

        Path(path).write_text(
            storage.export_history(days=days, format=format_name),
            encoding="utf-8",
        )

    def _clear_all(self):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Clear all history")
        box.setText("Delete all dictation history?")
        box.setInformativeText(
            "This permanently removes every transcription from the local database "
            f"AND deletes the daily .txt files in:\n\n{self.cfg.save_dir}\n\nThis cannot be undone."
        )
        box.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        yes_btn.setText("Delete all")
        yes_btn.setStyleSheet("color: #ff3b30; font-weight: 600;")

        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        result = storage.clear_all(save_dir=self.cfg.save_dir)
        self.detail.clear()
        self._last_loaded_at = 0.0  # invalidate cache
        self.refresh_async()

        info = QMessageBox(self)
        info.setIcon(QMessageBox.Icon.Information)
        info.setWindowTitle("History cleared")
        info.setText(
            f"Removed {result['rows_deleted']} entries from the database "
            f"and {result['files_deleted']} .txt files from disk."
        )
        info.exec()
