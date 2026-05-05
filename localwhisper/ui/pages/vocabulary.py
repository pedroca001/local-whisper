from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QHBoxLayout, QInputDialog, QVBoxLayout, QWidget

from ..widgets.card import Card
from ...config import Config


class VocabularyPage(QWidget):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 16, 28, 28)
        v.setSpacing(14)

        title = QLabel("Vocabulary")
        title.setObjectName("PageTitle")
        title.setStyleSheet("padding: 0;")
        v.addWidget(title)
        sub = QLabel("Custom words and phrases the model should recognize. Useful for names, jargon and product names.")
        sub.setObjectName("PageSubtitle")
        sub.setStyleSheet("padding: 0;")
        sub.setWordWrap(True)
        v.addWidget(sub)

        card = Card()
        card.add_title("Boost words")
        list_wrap = QWidget()
        lv = QVBoxLayout(list_wrap)
        lv.setContentsMargins(18, 6, 18, 14)
        lv.setSpacing(8)
        self.list = QListWidget()
        self.list.setMinimumHeight(180)
        self.list.addItems(getattr(cfg, "vocabulary", []) or [])
        lv.addWidget(self.list)

        row = QHBoxLayout()
        add = QPushButton("Add word…")
        add.clicked.connect(self._add)
        rem = QPushButton("Remove")
        rem.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        lv.addLayout(row)
        card.add_widget(list_wrap)
        v.addWidget(card)
        v.addStretch(1)

    def _add(self):
        text, ok = QInputDialog.getText(self, "Add vocabulary word", "Word or phrase:")
        if ok and text.strip():
            self.list.addItem(text.strip())
            self._save()

    def _remove(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._save()

    def _save(self):
        words = [self.list.item(i).text() for i in range(self.list.count())]
        self.cfg.vocabulary = words
        self.cfg.save()
