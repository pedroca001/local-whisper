from __future__ import annotations

from typing import Callable

from .base import TranscriberEngine
from .faster_whisper_engine import FasterWhisperEngine


def _make_whisper_turbo() -> TranscriberEngine:
    return FasterWhisperEngine("large-v3-turbo")


def _make_whisper_ultra() -> TranscriberEngine:
    return FasterWhisperEngine("large-v3")


def _make_parakeet_v3() -> TranscriberEngine:
    from .parakeet_engine import ParakeetEngine

    return ParakeetEngine()


MODELS: dict[str, dict] = {
    "whisper-turbo": {
        "factory": _make_whisper_turbo,
        "display_name": "Whisper Turbo (large-v3-turbo)",
        "subtitle": "Recommended — best balance of speed and PT-BR quality",
        "approx_vram_gb": 3.0,
        "speed_x_realtime": 100,
    },
    "parakeet-v3": {
        "factory": _make_parakeet_v3,
        "display_name": "Parakeet v3 Multilingual",
        "subtitle": "Fastest — NVIDIA TDT, ultra-low latency",
        "approx_vram_gb": 2.0,
        "speed_x_realtime": 300,
    },
    "whisper-ultra": {
        "factory": _make_whisper_ultra,
        "display_name": "Whisper Ultra (large-v3)",
        "subtitle": "Most accurate — for noisy or hard audio",
        "approx_vram_gb": 5.0,
        "speed_x_realtime": 50,
    },
}


def list_models() -> list[dict]:
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "factory"}} for k, v in MODELS.items()]


def get_engine(key: str) -> TranscriberEngine:
    if key not in MODELS:
        raise KeyError(f"Unknown model key: {key!r}. Available: {list(MODELS)}")
    factory: Callable[[], TranscriberEngine] = MODELS[key]["factory"]
    return factory()
