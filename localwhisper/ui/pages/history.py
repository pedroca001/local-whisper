from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
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
        sub = QLabel("Last 7 days of dictations. Click a row to expand.")
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        v.addWidget(sub)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._reload)
        bar.addWidget(self.search)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._reload)
        bar.addWidget(refresh)
        v.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Date", "Duration", "Model", "App", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellClicked.connect(self._show_detail)
        v.addWidget(self.table, stretch=1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)
        self.detail.setPlaceholderText("Select a transcription to view full text.")
        v.addWidget(self.detail)

        actions = QHBoxLayout()
        clear = QPushButton("Clear history…")
        clear.clicked.connect(self._clear_all)
        clear.setStyleSheet("color: #ff3b30;")
        actions.addWidget(clear)
        actions.addStretch(1)
        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy)
        actions.addWidget(copy)
        v.addLayout(actions)

        self._rows: list[dict] = []
        self._reload()

    def _reload(self, *args):
        q = self.search.text().strip()
        self._rows = storage.search(q, days=7) if q else storage.list_recent(7)
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            ts = r["started_at"].replace("T", " ")
            self.table.setItem(i, 0, QTableWidgetItem(ts))
            self.table.setItem(i, 1, QTableWidgetItem(f"{r['duration_ms']/1000:.1f}s"))
            self.table.setItem(i, 2, QTableWidgetItem(r.get("model", "")))
            self.table.setItem(i, 3, QTableWidgetItem(r.get("target_app") or "—"))
            text = (r["text"] or "").replace("\n", " ")
            if len(text) > 120:
                text = text[:120] + "…"
            self.table.setItem(i, 4, QTableWidgetItem(text))

    def _show_detail(self, row: int, _col: int):
        if 0 <= row < len(self._rows):
            self.detail.setPlainText(self._rows[row]["text"])

    def _copy(self):
        if self.detail.toPlainText():
            QGuiApplication.clipboard().setText(self.detail.toPlainText())

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
        # Style the destructive action
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        yes_btn.setText("Delete all")
        yes_btn.setStyleSheet("color: #ff3b30; font-weight: 600;")

        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        result = storage.clear_all(save_dir=self.cfg.save_dir)
        self.detail.clear()
        self._reload()

        info = QMessageBox(self)
        info.setIcon(QMessageBox.Icon.Information)
        info.setWindowTitle("History cleared")
        info.setText(
            f"Removed {result['rows_deleted']} entries from the database "
            f"and {result['files_deleted']} .txt files from disk."
        )
        info.exec()

    def refresh_async(self):
        QTimer.singleShot(0, self._reload)
