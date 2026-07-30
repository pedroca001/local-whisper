"""Exercise the quit barrier around delayed delivery actions."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QTimer

from localwhisper.app import App
from localwhisper.session import DictationState


class _Harness:
    def __init__(self) -> None:
        self._quit_pending = True
        self._enter_pending = True
        self._clipboard_restore_pending = True
        self.controller = SimpleNamespace(state=DictationState.IDLE)
        self.quit_calls = 0

    def _do_quit(self) -> None:
        self.quit_calls += 1


def main() -> int:
    app = QCoreApplication.instance() or QCoreApplication([])
    harness = _Harness()

    App._resume_pending_quit(harness)
    app.processEvents()
    assert harness.quit_calls == 0

    harness._enter_pending = False
    App._resume_pending_quit(harness)
    app.processEvents()
    assert harness.quit_calls == 0

    harness._clipboard_restore_pending = False
    App._resume_pending_quit(harness)
    QTimer.singleShot(20, app.quit)
    app.exec()
    assert harness.quit_calls == 1

    recording = _Harness()
    recording._enter_pending = False
    recording.controller.state = DictationState.RECORDING
    App._resume_pending_quit(recording)
    app.processEvents()
    assert recording.quit_calls == 0
    recording._clipboard_restore_pending = False
    App._resume_pending_quit(recording)
    QTimer.singleShot(20, app.quit)
    app.exec()
    assert recording.quit_calls == 1

    print(
        "delivery-quit-ok enter=completed clipboard=restored "
        "idle_quit=1 recording_quit=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
