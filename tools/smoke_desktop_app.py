"""Launch the real tray/settings stack briefly, then shut it down cleanly."""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from localwhisper import diagnostics, gpu
from localwhisper.app import App
from localwhisper.config import Config


def main() -> int:
    diagnostics.setup_logging()
    gpu.setup()
    cfg = Config.load()
    cfg.onboarding_complete = True
    cfg.hotkey_toggle = "ctrl+shift+f12"
    cfg.hotkey_paste_last = "win+alt+f12"
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    product = App(app, cfg)
    product.window.show()
    QTimer.singleShot(100, product.overlay.show_at_top_center)
    QTimer.singleShot(350, product.overlay.fade_out_and_hide)
    QTimer.singleShot(700, product.overlay.show_at_top_center)
    QTimer.singleShot(950, product.overlay.fade_out_and_hide)
    QTimer.singleShot(1500, product._do_quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
