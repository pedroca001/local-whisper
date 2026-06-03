from __future__ import annotations

from typing import Callable

from .base import TranscriberEngine
from .faster_whisper_engine import FasterWhisperEngine


def _make_whisper_turbo(
    compute_device: str = "auto",
    compute_type: str = "float16",
    models_dir: str | None = None,
) -> TranscriberEngine:
    return FasterWhisperEngine("large-v3-turbo", compute_type=compute_type, compute_device=compute_device, models_dir=models_dir)


def _make_whisper_ultra(
    compute_device: str = "auto",
    compute_type: str = "float16",
    models_dir: str | None = None,
) -> TranscriberEngine:
    return FasterWhisperEngine("large-v3", compute_type=compute_type, compute_device=compute_device, models_dir=models_dir)


def _make_parakeet_v3(
    compute_device: str = "auto",
    compute_type: str = "float16",
    models_dir: str | None = None,
) -> TranscriberEngine:
    from .parakeet_engine import ParakeetEngine

    return ParakeetEngine()


MODELS: dict[str, dict] = {
    "whisper-turbo": {
        "factory": _make_whisper_turbo,
        "display_name": "Whisper Turbo (large-v3-turbo)",
        "subtitle": "Recommended — best balance of speed and PT-BR quality",
        "approx_vram_gb": 3.0,
        "speed_x_realtime": 100,
        "cache_kind": "huggingface",
        "repo_id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "installable": True,
    },
    "parakeet-v3": {
        "factory": _make_parakeet_v3,
        "display_name": "Parakeet v3 Multilingual",
        "subtitle": "Fastest — NVIDIA TDT, ultra-low latency",
        "approx_vram_gb": 2.0,
        "speed_x_realtime": 300,
        "cache_kind": "nemo",
        "repo_id": "nvidia/parakeet-tdt-0.6b-v3",
        "cache_subdir": "parakeet-v3",
        "installable": True,
    },
    "whisper-ultra": {
        "factory": _make_whisper_ultra,
        "display_name": "Whisper Ultra (large-v3)",
        "subtitle": "Most accurate — for noisy or hard audio",
        "approx_vram_gb": 5.0,
        "speed_x_realtime": 50,
        "cache_kind": "huggingface",
        "repo_id": "Systran/faster-whisper-large-v3",
        "installable": True,
    },
}


def list_models() -> list[dict]:
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "factory"}} for k, v in MODELS.items()]


def get_engine(
    key: str,
    compute_device: str = "auto",
    compute_type: str = "float16",
    models_dir: str | None = None,
) -> TranscriberEngine:
    if key not in MODELS:
        raise KeyError(f"Unknown model key: {key!r}. Available: {list(MODELS)}")
    factory: Callable[[str, str, str | None], TranscriberEngine] = MODELS[key]["factory"]
    return factory(compute_device, compute_type, models_dir)
