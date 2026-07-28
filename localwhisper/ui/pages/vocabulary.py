from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from ...config import Config
from ..widgets.card import Card


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

        replace_card = Card()
        replace_card.add_title("Corrections")
        replace_wrap = QWidget()
        rv = QVBoxLayout(replace_wrap)
        rv.setContentsMargins(18, 6, 18, 14)
        rv.setSpacing(8)
        self.replacements = QListWidget()
        self.replacements.setMinimumHeight(130)
        self._load_replacements()
        rv.addWidget(self.replacements)

        replace_row = QHBoxLayout()
        add_replace = QPushButton("Add correction...")
        add_replace.clicked.connect(self._add_replacement)
        rem_replace = QPushButton("Remove")
        rem_replace.clicked.connect(self._remove_replacement)
        replace_row.addWidget(add_replace)
        replace_row.addWidget(rem_replace)
        replace_row.addStretch(1)
        rv.addLayout(replace_row)
        replace_card.add_widget(replace_wrap)
        v.addWidget(replace_card)
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

    def _load_replacements(self):
        self.replacements.clear()
        for rule in getattr(self.cfg, "vocabulary_replacements", []) or []:
            src = str(rule.get("from", "")).strip()
            dst = str(rule.get("to", "")).strip()
            if src and dst:
                self.replacements.addItem(f"{src} -> {dst}")

    def _add_replacement(self):
        src, ok = QInputDialog.getText(self, "Add correction", "When LocalWhisper hears:")
        if not ok or not src.strip():
            return
        dst, ok = QInputDialog.getText(self, "Add correction", "Write instead:")
        if not ok or not dst.strip():
            return
        rules = list(getattr(self.cfg, "vocabulary_replacements", []) or [])
        rules.append({"from": src.strip(), "to": dst.strip()})
        self.cfg.vocabulary_replacements = rules
        self.cfg.save()
        self._load_replacements()

    def _remove_replacement(self):
        selected = {self.replacements.row(it) for it in self.replacements.selectedItems()}
        rules = [
            rule
            for i, rule in enumerate(getattr(self.cfg, "vocabulary_replacements", []) or [])
            if i not in selected
        ]
        self.cfg.vocabulary_replacements = rules
        self.cfg.save()
        self._load_replacements()
