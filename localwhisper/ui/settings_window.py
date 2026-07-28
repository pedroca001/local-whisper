from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from .icons import all_icons
from .pages.configuration import ConfigurationPage
from .pages.diagnostics import DiagnosticsPage
from .pages.history import HistoryPage
from .pages.home import HomePage
from .pages.modes import ModesPage
from .pages.sound import SoundPage
from .pages.transcribe_file import TranscribeFilePage
from .pages.vocabulary import VocabularyPage


class SettingsWindow(QMainWindow):
    hotkey_changed = Signal(str)
    paste_last_hotkey_changed = Signal(str)
    config_changed = Signal()
    record_now_requested = Signal()

    SIDEBAR_ITEMS = [
        "Home",
        "Modes",
        "Transcribe File",
        "Vocabulary",
        "History",
        "Sound",
        "Configuration",
        "Diagnostics",
    ]

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("LocalWhisper")
        self.setMinimumSize(1040, 680)
        self.resize(1120, 720)
        self.setObjectName("MainWindow")

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Sidebar ----
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(244)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 16, 14, 16)
        sl.setSpacing(12)

        brand = QFrame()
        brand.setObjectName("Brand")
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(2, 0, 2, 8)
        bl.setSpacing(10)
        mark = QLabel("LW")
        mark.setObjectName("BrandMark")
        mark.setAlignment(Qt.AlignCenter)
        bl.addWidget(mark)
        brand_text = QWidget()
        btl = QVBoxLayout(brand_text)
        btl.setContentsMargins(0, 0, 0, 0)
        btl.setSpacing(1)
        header = QLabel("LocalWhisper")
        header.setObjectName("SidebarHeader")
        subheader = QLabel("Offline dictation")
        subheader.setObjectName("SidebarSubheader")
        btl.addWidget(header)
        btl.addWidget(subheader)
        bl.addWidget(brand_text, stretch=1)
        sl.addWidget(brand)

        self.list = QListWidget()
        self.list.setIconSize(QSize(20, 20))
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(4)
        self.list.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        icons = all_icons()
        for label in self.SIDEBAR_ITEMS:
            item = QListWidgetItem(label)
            if label in icons:
                item.setIcon(icons[label])
            item.setSizeHint(QSize(0, 42))
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.setFixedHeight(440)
        self.list.currentRowChanged.connect(self._switch_page)
        sl.addWidget(self.list)
        sl.addStretch(1)

        footer = QFrame()
        footer.setObjectName("SidebarFooter")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(12, 12, 12, 12)
        fl.setSpacing(6)
        self.footer_state = QLabel("Ready")
        self.footer_state.setObjectName("FooterState")
        self.footer_model = QLabel("")
        self.footer_model.setObjectName("FooterMeta")
        self.footer_hotkey = QLabel("")
        self.footer_hotkey.setObjectName("FooterMeta")
        fl.addWidget(self.footer_state)
        fl.addWidget(self.footer_model)
        fl.addWidget(self.footer_hotkey)
        sl.addWidget(footer)

        outer.addWidget(side)

        # ---- Content ----
        content = QWidget()
        content.setObjectName("ContentArea")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("PageStack")
        cl.addWidget(self.stack)
        outer.addWidget(content, stretch=1)

        # Pages — order MUST match SIDEBAR_ITEMS
        self.page_home = HomePage(cfg, on_record_now=lambda: self.record_now_requested.emit())
        self.page_modes = ModesPage(cfg)
        self.page_transcribe_file = TranscribeFilePage(cfg)
        self.page_vocabulary = VocabularyPage(cfg)
        self.page_config = ConfigurationPage(cfg)
        self.page_sound = SoundPage(cfg)
        self.page_history = HistoryPage(cfg)
        self.page_diagnostics = DiagnosticsPage()

        self._page_by_name = {
            "Home": self.page_home,
            "Modes": self.page_modes,
            "Transcribe File": self.page_transcribe_file,
            "Vocabulary": self.page_vocabulary,
            "History": self.page_history,
            "Sound": self.page_sound,
            "Configuration": self.page_config,
            "Diagnostics": self.page_diagnostics,
        }
        for name in self.SIDEBAR_ITEMS:
            self.stack.addWidget(self._scroll_page(self._page_by_name[name]))

        self.page_modes.config_changed.connect(self._on_config_changed)
        self.page_config.config_changed.connect(self._on_config_changed)
        self.page_sound.config_changed.connect(self._on_config_changed)
        self.page_config.hotkey_changed.connect(self.hotkey_changed.emit)
        self.page_config.paste_last_hotkey_changed.connect(self.paste_last_hotkey_changed.emit)

        self._apply_qss()
        self._refresh_sidebar_status()

    def _apply_qss(self) -> None:
        qss_path = Path(__file__).parent / "style.qss"
        try:
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    def _scroll_page(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _switch_page(self, idx: int) -> None:
        if idx < 0 or idx >= self.stack.count():
            return
        self.stack.setCurrentIndex(idx)
        scroll = self.stack.widget(idx)
        if isinstance(scroll, QScrollArea):
            QTimer.singleShot(0, lambda s=scroll: s.verticalScrollBar().setValue(0))
        name = self.SIDEBAR_ITEMS[idx] if 0 <= idx < len(self.SIDEBAR_ITEMS) else None
        if name == "History":
            self.page_history.refresh_async()
        elif name == "Diagnostics":
            self.page_diagnostics.refresh()
        elif name == "Home":
            self.page_home.refresh()

    def _on_config_changed(self) -> None:
        self.page_home.refresh()
        self._refresh_sidebar_status()
        self.config_changed.emit()

    def _refresh_sidebar_status(self) -> None:
        hotkey = " + ".join(p.capitalize() for p in self.cfg.hotkey_toggle.split("+") if p)
        self.footer_model.setText(f"Model: {self.cfg.model}")
        self.footer_hotkey.setText(f"Hotkey: {hotkey}")
