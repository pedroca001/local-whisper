from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from .icons import all_icons
from .pages.configuration import ConfigurationPage
from .pages.history import HistoryPage
from .pages.home import HomePage
from .pages.modes import ModesPage
from .pages.sound import SoundPage
from .pages.vocabulary import VocabularyPage


def _attach_card_shadows(root: QWidget) -> None:
    """Walk a tree of widgets and add a soft drop shadow to every QFrame#Card."""
    for frame in root.findChildren(QFrame):
        if frame.objectName() == "Card":
            eff = QGraphicsDropShadowEffect(frame)
            eff.setBlurRadius(18)
            eff.setOffset(0, 2)
            eff.setColor(QColor(0, 0, 0, 22))
            frame.setGraphicsEffect(eff)


class SettingsWindow(QMainWindow):
    hotkey_changed = Signal(str)
    config_changed = Signal()
    record_now_requested = Signal()

    SIDEBAR_ITEMS = ["Home", "Modes", "Vocabulary", "Configuration", "Sound", "History"]

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("LocalWhisper")
        self.setMinimumSize(900, 600)
        self.setObjectName("MainWindow")

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Sidebar ----
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        header = QLabel("LocalWhisper")
        header.setObjectName("SidebarHeader")
        sl.addWidget(header)

        self.list = QListWidget()
        self.list.setIconSize(QSize(20, 20))
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.list.setUniformItemSizes(True)
        self.list.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        icons = all_icons()
        for label in self.SIDEBAR_ITEMS:
            item = QListWidgetItem(label)
            if label in icons:
                item.setIcon(icons[label])
            item.setSizeHint(QSize(0, 36))
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.setFixedHeight(36 * len(self.SIDEBAR_ITEMS) + 16)
        self.list.currentRowChanged.connect(self._switch_page)
        sl.addWidget(self.list)
        sl.addStretch(1)
        outer.addWidget(side)

        # ---- Content ----
        content = QWidget()
        content.setObjectName("ContentArea")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.stack = QStackedWidget()
        cl.addWidget(self.stack)
        outer.addWidget(content, stretch=1)

        # Pages — order MUST match SIDEBAR_ITEMS
        self.page_home = HomePage(cfg, on_record_now=lambda: self.record_now_requested.emit())
        self.page_modes = ModesPage(cfg)
        self.page_vocabulary = VocabularyPage(cfg)
        self.page_config = ConfigurationPage(cfg)
        self.page_sound = SoundPage(cfg)
        self.page_history = HistoryPage(cfg)

        self._page_by_name = {
            "Home": self.page_home,
            "Modes": self.page_modes,
            "Vocabulary": self.page_vocabulary,
            "Configuration": self.page_config,
            "Sound": self.page_sound,
            "History": self.page_history,
        }
        for name in self.SIDEBAR_ITEMS:
            self.stack.addWidget(self._page_by_name[name])

        self.page_modes.config_changed.connect(self._on_config_changed)
        self.page_config.config_changed.connect(self._on_config_changed)
        self.page_sound.config_changed.connect(self._on_config_changed)
        self.page_config.hotkey_changed.connect(self.hotkey_changed.emit)

        self._apply_qss()
        _attach_card_shadows(self)

    def _apply_qss(self) -> None:
        qss_path = Path(__file__).parent / "style.qss"
        try:
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    def _switch_page(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        name = self.SIDEBAR_ITEMS[idx] if 0 <= idx < len(self.SIDEBAR_ITEMS) else None
        if name == "History":
            self.page_history.refresh_async()
        elif name == "Home":
            self.page_home.refresh()

    def _on_config_changed(self) -> None:
        self.page_home.refresh()
        self.config_changed.emit()
