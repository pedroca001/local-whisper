"""Dictation session state and immutable result snapshots."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic


class DictationState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    INJECTING = "injecting"
    ERROR = "error"


@dataclass
class DictationSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_monotonic: float = field(default_factory=monotonic)
    target_hwnd: int = 0
    target_focus_hwnd: int = 0
    target_app: str | None = None
    target_title: str | None = None
    can_inject: bool = False
    mode: dict = field(default_factory=dict)
    streaming: bool = False
    stream_stop: threading.Event = field(default_factory=threading.Event, repr=False)
    stream_thread: threading.Thread | None = field(default=None, repr=False)
    stream_started: bool = False
    stream_samples_pushed: int = 0
    engine_ready: threading.Event = field(default_factory=threading.Event, repr=False)
    engine_load_error: str | None = None


@dataclass(frozen=True)
class DictationResult:
    session: DictationSession
    text: str
    duration_ms: int
    needs_recovery: bool = False


class SessionState:
    """Thread-safe transition guard for the recording lifecycle."""

    _ALLOWED = {
        DictationState.IDLE: {DictationState.RECORDING},
        DictationState.RECORDING: {
            DictationState.PROCESSING,
            DictationState.IDLE,
            DictationState.ERROR,
        },
        DictationState.PROCESSING: {
            DictationState.INJECTING,
            DictationState.IDLE,
            DictationState.ERROR,
        },
        DictationState.INJECTING: {
            DictationState.IDLE,
            DictationState.ERROR,
        },
        DictationState.ERROR: {DictationState.IDLE},
    }

    def __init__(self):
        self._value = DictationState.IDLE
        self._lock = threading.RLock()

    @property
    def value(self) -> DictationState:
        with self._lock:
            return self._value

    def transition(self, target: DictationState, *, force: bool = False) -> bool:
        with self._lock:
            if target == self._value:
                return True
            if not force and target not in self._ALLOWED[self._value]:
                return False
            self._value = target
            return True

    @property
    def busy(self) -> bool:
        return self.value != DictationState.IDLE
