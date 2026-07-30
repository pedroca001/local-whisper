from __future__ import annotations

import time

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
)
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
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ... import storage
from ...config import Config

FilterRequest = tuple[str, int, bool]
LoadRequest = tuple[int, FilterRequest]


class _HistoryLoader(QObject):
    """Runs the SQLite query off the UI thread and emits the rows."""

    loaded = Signal(list, object, dict)  # rows, request tuple, stats

    def __init__(self, request: LoadRequest) -> None:
        super().__init__()
        self.request = request

    def run(self) -> None:
        request = self.request
        _generation, filter_request = request
        query, days, favorites_only = filter_request
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
        self.loaded.emit(rows, request, summary)


class _HistoryTableModel(QAbstractTableModel):
    """Virtualized history rows; only visible cells are formatted by Qt."""

    HEADERS = ("", "Date", "Duration", "Model", "App", "Text")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        row = self._rows[index.row()]
        column = index.column()
        if column == 0:
            return "★" if row.get("favorite") else ""
        if column == 1:
            return str(row["started_at"]).replace("T", " ")
        if column == 2:
            return f"{row['duration_ms'] / 1000:.1f}s"
        if column == 3:
            return row.get("model", "")
        if column == 4:
            return row.get("target_app") or "—"
        text = str(row.get("text") or "").replace("\n", " ")
        return text[:120] + "…" if len(text) > 120 else text

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return None


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
        refresh.clicked.connect(lambda _checked=False: self._invalidate_and_refresh())
        bar.addWidget(refresh)
        v.addLayout(bar)

        self.status_label = QLabel("Loading…")
        self.status_label.setStyleSheet("color: #888; padding: 4px 0;")
        v.addWidget(self.status_label)
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #555; padding: 0 0 4px 0;")
        v.addWidget(self.stats_label)

        self.table = QTableView()
        self._table_model = _HistoryTableModel(self.table)
        self.table.setModel(self._table_model)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.clicked.connect(self._show_detail)
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
        self._last_loaded_at: float = 0.0
        self._last_loaded_request: FilterRequest | None = None
        self._generation = 0
        self._stale = True

        # Debounce search typing so we don't spawn a thread per keystroke.
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(180)
        self._search_debounce.timeout.connect(self.refresh_async)

    # ── data flow ────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._stale:
            QTimer.singleShot(0, self.refresh_async)

    def _on_search_changed(self, _text: str) -> None:
        self._invalidate()
        self._search_debounce.start()

    def _invalidate_and_refresh(self) -> None:
        self.invalidate_and_refresh()

    def invalidate_and_refresh(self) -> None:
        self._invalidate()
        self.refresh_async()

    def _invalidate(self) -> None:
        self._generation += 1
        self._stale = True
        self._last_loaded_at = 0.0

    def _current_request(self) -> FilterRequest:
        return (
            self.search.text().strip(),
            self.cfg.history_retention_days or 3650,
            self.favorites_only.isChecked(),
        )

    def refresh_async(self) -> None:
        if not self.isVisible():
            self._stale = True
            return
        request = self._current_request()
        # 2-second cache: if same query was just loaded, skip.
        if (
            not self._stale
            and self._last_loaded_request == request
            and (time.monotonic() - self._last_loaded_at) < 2.0
            and self._thread is None
        ):
            return
        if self._thread is not None and self._thread.isRunning():
            # The latest complete filter state is re-read when the worker finishes.
            return
        self._spawn_loader(request)

    def _spawn_loader(self, request: FilterRequest) -> None:
        self.status_label.setText("Loading…")
        self.status_label.setVisible(True)

        thread = QThread(self)
        loader = _HistoryLoader((self._generation, request))
        loader.moveToThread(thread)
        loader.loaded.connect(self._on_loaded)
        thread.started.connect(loader.run)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(loader.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._loader = loader
        thread.start()

    def _on_loaded(
        self,
        rows: list,
        request: LoadRequest,
        summary: dict,
    ) -> None:
        generation, filter_request = request
        if (
            generation != self._generation
            or filter_request != self._current_request()
        ):
            self._stale = True
            if self._thread is not None:
                self._thread.quit()
            return
        self._rows = rows
        self._apply_rows(rows)
        if summary:
            self.stats_label.setText(
                f"{summary['sessions']} sessions · {summary['words']} words · "
                f"{summary['duration_minutes']:.1f} min · {summary['words_per_minute']:.0f} wpm"
            )
        self._last_loaded_at = time.monotonic()
        self._last_loaded_request = filter_request
        self._stale = False

        if self._thread is not None:
            self._thread.quit()

    def _on_thread_finished(self) -> None:
        thread = self.sender()
        if thread is not self._thread:
            return
        self._thread = None
        self._loader = None
        current_request = self._current_request()
        if self._stale or current_request != self._last_loaded_request:
            self._stale = True
            if self.isVisible():
                self._spawn_loader(current_request)

    def _apply_rows(self, rows: list[dict]) -> None:
        self._table_model.set_rows(rows)

        if rows:
            self.status_label.setVisible(False)
        else:
            self.status_label.setText("No matching transcriptions.")
            self.status_label.setVisible(True)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        thread = self._thread
        if thread is None or not thread.isRunning():
            return True
        thread.requestInterruption()
        thread.quit()
        return bool(thread.wait(timeout_ms))

    # ── interactions ─────────────────────────────────────────────────────────

    def _show_detail(self, index: QModelIndex) -> None:
        row = index.row()
        if 0 <= row < len(self._rows):
            self.detail.setPlainText(self._rows[row]["text"])

    def _copy(self):
        if self.detail.toPlainText():
            QGuiApplication.clipboard().setText(self.detail.toPlainText())

    def _selected_row(self) -> dict | None:
        row = self.table.currentIndex().row()
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
        self.invalidate_and_refresh()

        info = QMessageBox(self)
        info.setIcon(QMessageBox.Icon.Information)
        info.setWindowTitle("History cleared")
        info.setText(
            f"Removed {result['rows_deleted']} entries from the database "
            f"and {result['files_deleted']} .txt files from disk."
        )
        info.exec()
