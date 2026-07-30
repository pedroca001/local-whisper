"""Render a settings page offscreen for fast visual regression checks."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from localwhisper.config import Config  # noqa: E402
from localwhisper.ui.onboarding import OnboardingDialog  # noqa: E402
from localwhisper.ui.settings_window import SettingsWindow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--page", default="Home", choices=SettingsWindow.SIDEBAR_ITEMS)
    parser.add_argument("--onboarding", action="store_true")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([])
    cfg = Config.load()
    window = OnboardingDialog(cfg) if args.onboarding else SettingsWindow(cfg)
    if not args.onboarding:
        window.list.setCurrentRow(window.SIDEBAR_ITEMS.index(args.page))
    window.show()
    app.processEvents()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(output)):
        raise RuntimeError(f"Could not write preview: {output}")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
