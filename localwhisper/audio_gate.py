from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AudioActivity:
    duration_s: float
    rms: float
    peak: float
    voiced_ratio: float

    @property
    def has_voice(self) -> bool:
        if self.duration_s < 0.35:
            return False
        if self.peak < 0.012:
            return False
        if self.rms < 0.0018:
            return False
        return self.voiced_ratio >= 0.015


def analyze_audio_activity(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> AudioActivity:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return AudioActivity(0.0, 0.0, 0.0, 0.0)
    duration_s = float(audio.size) / float(sample_rate)
    abs_audio = np.abs(audio)
    rms = float(np.sqrt(np.mean(audio * audio))) if audio.size else 0.0
    peak = float(np.max(abs_audio)) if audio.size else 0.0
    voiced_ratio = float(np.mean(abs_audio > 0.01)) if audio.size else 0.0
    return AudioActivity(duration_s, rms, peak, voiced_ratio)


def looks_like_silence(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bool:
    return not analyze_audio_activity(audio, sample_rate=sample_rate).has_voice
