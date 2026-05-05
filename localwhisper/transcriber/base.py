from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

import numpy as np

OnDeltaFn = Callable[[str], None]


class TranscriberEngine(ABC):
    """Common interface for ASR engines (Whisper, Parakeet, ...)."""

    name: str = "base"
    display_name: str = "Base"
    approx_vram_gb: float = 0.0
    speed_x_realtime: int = 0

    @abstractmethod
    def load(self) -> None:
        """Load model weights into memory/VRAM. May download on first call."""

    @abstractmethod
    def unload(self) -> None:
        """Free GPU memory."""

    @abstractmethod
    def is_loaded(self) -> bool:
        ...

    @abstractmethod
    def transcribe_full(self, audio: np.ndarray, language: str = "pt") -> str:
        """Transcribe a full audio buffer at once. Used for final-dump mode."""

    def start_stream(self, language: str = "pt", on_delta: Optional[OnDeltaFn] = None) -> None:
        """Begin a streaming session. Default: no-op (engine that only supports full)."""
        self._stream_lang = language
        self._stream_on_delta = on_delta
        self._stream_buffer: list[np.ndarray] = []

    def push_chunk(self, samples: np.ndarray) -> None:
        """Feed an audio chunk during streaming. Default: just buffer."""
        if not hasattr(self, "_stream_buffer"):
            self._stream_buffer = []
        self._stream_buffer.append(samples)

    def finalize_stream(self) -> str:
        """End streaming, return final transcription."""
        if not hasattr(self, "_stream_buffer") or not self._stream_buffer:
            return ""
        audio = np.concatenate(self._stream_buffer)
        self._stream_buffer = []
        return self.transcribe_full(audio, language=getattr(self, "_stream_lang", "pt"))
