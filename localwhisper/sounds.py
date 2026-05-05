"""Soft, synthesized notification sounds for recording start/stop.

We generate WAV files once on first use (cached in %LOCALAPPDATA%\\LocalWhisper\\sounds\\)
and play them asynchronously via sounddevice. Pure sine waves with a smooth raised-cosine
envelope — much more pleasant than winsound.Beep (which is square wave).
"""
from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from .config import _local_appdata_dir

_output_device_name: str | None = None
_volume: float = 0.8


def set_output_device(name: str | None) -> None:
    global _output_device_name
    _output_device_name = name


def set_volume(vol: float) -> None:
    global _volume
    _volume = max(0.0, min(1.0, vol))

SAMPLE_RATE = 44100
SOUNDS_DIR = _local_appdata_dir() / "sounds"
SOUNDS_DIR.mkdir(parents=True, exist_ok=True)


def _envelope(n: int, attack_ms: float = 8.0, release_ms: float = 80.0) -> np.ndarray:
    """Raised-cosine attack + exponential release. Removes the harsh click."""
    t = np.linspace(0, n / SAMPLE_RATE * 1000, n, endpoint=False)
    attack_n = max(1, int(SAMPLE_RATE * attack_ms / 1000))
    env = np.ones(n, dtype=np.float32)
    if attack_n < n:
        env[:attack_n] = 0.5 * (1 - np.cos(np.pi * np.arange(attack_n) / attack_n))
    # Exponential decay for the rest
    release_t = t / release_ms
    env *= np.exp(-release_t * 1.6)
    return env


def _tone(freq: float, duration_ms: float, *, harmonic_strength: float = 0.18) -> np.ndarray:
    n = int(SAMPLE_RATE * duration_ms / 1000)
    t = np.arange(n) / SAMPLE_RATE
    sig = np.sin(2 * np.pi * freq * t)
    # Add a touch of the 5th harmonic for warmth (like a tuning fork)
    sig += harmonic_strength * np.sin(2 * np.pi * freq * 1.5 * t)
    sig /= 1.0 + harmonic_strength
    sig *= _envelope(n)
    return sig.astype(np.float32)


def _write_wav(path: Path, samples: np.ndarray, gain: float = 0.45) -> None:
    samples = np.clip(samples * gain, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


def _make_chord(notes: list[tuple[float, float]], gap_ms: float = 35.0) -> np.ndarray:
    """notes: list of (freq, duration_ms). Plays them with a small gap, slightly overlapping."""
    parts = [_tone(f, d) for f, d in notes]
    gap_n = int(SAMPLE_RATE * gap_ms / 1000)
    total_n = sum(p.size for p in parts) - gap_n * (len(parts) - 1)
    out = np.zeros(total_n, dtype=np.float32)
    pos = 0
    for p in parts:
        end = pos + p.size
        out[pos:end] += p
        pos = end - gap_n
    return out


def _ensure_files() -> tuple[Path, Path, Path]:
    start = SOUNDS_DIR / "start.wav"
    stop = SOUNDS_DIR / "stop.wav"
    cancel = SOUNDS_DIR / "cancel.wav"

    if not start.exists():
        # C5 -> G5 — clean ascending soft chime, very brief
        _write_wav(start, _make_chord([(523.25, 90), (783.99, 130)], gap_ms=20))
    if not stop.exists():
        # G5 -> C5 — descending, slightly longer release
        _write_wav(stop, _make_chord([(783.99, 90), (523.25, 150)], gap_ms=20))
    if not cancel.exists():
        # Single low pop
        _write_wav(cancel, _tone(330, 110))

    return start, stop, cancel


def _resolve_output_device() -> int | None:
    if _output_device_name is None:
        return None
    try:
        devices = sd.query_devices()
        for idx, d in enumerate(devices):
            if d["name"] == _output_device_name and d.get("max_output_channels", 0) > 0:
                return idx
    except Exception:
        pass
    return None


def _play_async(path: Path) -> None:
    if not path.exists():
        return

    def _run():
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                rate = wf.getframerate()
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
            data = data * _volume
            device = _resolve_output_device()
            with sd.OutputStream(samplerate=rate, channels=1, dtype="float32", device=device) as stream:
                stream.write(data)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


_START, _STOP, _CANCEL = _ensure_files()


def play_start() -> None:
    _play_async(_START)


def play_stop() -> None:
    _play_async(_STOP)


def play_cancel() -> None:
    _play_async(_CANCEL)
