from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
BLOCK_MS = 30
BLOCK_SIZE = SAMPLE_RATE * BLOCK_MS // 1000


def list_input_devices() -> list[dict]:
    devices = sd.query_devices()
    out = []
    for idx, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            out.append({
                "index": idx,
                "name": d["name"],
                "default_samplerate": d.get("default_samplerate", 48000),
            })
    return out


def list_output_devices() -> list[dict]:
    devices = sd.query_devices()
    out = []
    for idx, d in enumerate(devices):
        if d.get("max_output_channels", 0) > 0:
            out.append({
                "index": idx,
                "name": d["name"],
            })
    return out


def get_default_input_device_name() -> str:
    try:
        idx = sd.default.device[0]
        if idx is None or idx < 0:
            return "System default microphone"
        return sd.query_devices(idx)["name"]
    except Exception:
        return "System default microphone"


class Recorder:
    """Captures audio from the selected input device into a thread-safe queue.

    Audio is delivered as float32 mono at 16kHz, in BLOCK_MS chunks.
    """

    def __init__(self, device: Optional[int | str] = None, on_block: Optional[Callable[[np.ndarray], None]] = None):
        self.device = device
        self.on_block = on_block
        self._stream: Optional[sd.InputStream] = None
        self._chunks: queue.Queue[np.ndarray] = queue.Queue()
        self._lock = threading.Lock()
        self._running = False
        self._all_audio: list[np.ndarray] = []

    def _callback(self, indata, frames, time, status):
        # indata shape: (frames, channels)
        mono = indata[:, 0].astype(np.float32, copy=True) if indata.ndim > 1 else indata.astype(np.float32, copy=True)
        with self._lock:
            self._all_audio.append(mono)
        self._chunks.put(mono)
        if self.on_block:
            try:
                self.on_block(mono)
            except Exception:
                pass

    def start(self) -> None:
        if self._running:
            return
        with self._lock:
            self._all_audio = []
        self._chunks = queue.Queue()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()
        self._running = True

    def stop(self) -> np.ndarray:
        if not self._running:
            return np.zeros(0, dtype=np.float32)
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self._running = False
        with self._lock:
            if self._all_audio:
                return np.concatenate(self._all_audio)
            return np.zeros(0, dtype=np.float32)

    def get_chunk(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        try:
            return self._chunks.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def running(self) -> bool:
        return self._running
