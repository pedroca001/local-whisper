"""Speaker diarization wrapper around pyannote.audio.

pyannote/speaker-diarization-3.1 is free but gated:
    1. Visit https://huggingface.co/pyannote/speaker-diarization-3.1 and accept the
       user-conditions (the same goes for pyannote/segmentation-3.0).
    2. Generate a free access token at https://huggingface.co/settings/tokens
       (a read-only "User Access Token" is enough).
    3. Paste it into LocalWhisper's Configuration page or set the HF_TOKEN env var.

The model is downloaded once into the HuggingFace cache (~70 MB total).
GPU is used automatically when torch.cuda.is_available(); else CPU (slower).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import numpy as np


class DiarizationUnavailable(RuntimeError):
    """Raised when pyannote.audio cannot be loaded (missing dep, no token, etc.)."""


class DiarizationPipeline:
    """Lazy-loaded pyannote speaker-diarization pipeline."""

    MODEL_ID = "pyannote/speaker-diarization-3.1"

    def __init__(self, hf_token: Optional[str] = None):
        self._token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
        self._pipeline = None
        self._lock = threading.Lock()
        self._device = "cpu"

    def is_loaded(self) -> bool:
        return self._pipeline is not None

    def load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from pyannote.audio import Pipeline as _Pipeline  # type: ignore
        except Exception as exc:
            raise DiarizationUnavailable(
                "pyannote.audio is not installed. Run:\n"
                "    pip install pyannote.audio\n\n"
                f"(import error: {exc})"
            ) from exc

        if not self._token:
            raise DiarizationUnavailable(
                "Speaker diarization needs a HuggingFace access token.\n"
                "1. Accept the model terms at https://huggingface.co/pyannote/speaker-diarization-3.1\n"
                "2. Create a free token at https://huggingface.co/settings/tokens\n"
                "3. Paste it in LocalWhisper → Configuration → HuggingFace token."
            )

        with self._lock:
            try:
                pipeline = _Pipeline.from_pretrained(self.MODEL_ID, use_auth_token=self._token)
            except Exception as exc:
                raise DiarizationUnavailable(
                    "Failed to load pyannote/speaker-diarization-3.1.\n"
                    "Make sure you accepted the model conditions on HuggingFace and that your token is valid.\n"
                    f"(error: {exc})"
                ) from exc

            # Move to GPU if torch + CUDA available
            try:
                import torch
                if torch.cuda.is_available():
                    pipeline.to(torch.device("cuda"))
                    self._device = "cuda"
                    logging.info("pyannote pipeline running on CUDA")
                else:
                    self._device = "cpu"
                    logging.info("pyannote pipeline running on CPU")
            except Exception:
                logging.info("pyannote pipeline running on CPU (torch.cuda not available)")

            self._pipeline = pipeline

    def diarize(
        self,
        audio: np.ndarray,
        *,
        sample_rate: int = 16000,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[tuple[float, float, str]]:
        """Return [(start_s, end_s, raw_speaker_label), …]."""
        if self._pipeline is None:
            self.load()

        # pyannote expects a torch tensor or a dict {"waveform": tensor, "sample_rate": int}
        try:
            import torch
        except Exception as exc:
            raise DiarizationUnavailable(f"PyTorch is required for diarization: {exc}") from exc

        waveform = torch.from_numpy(np.ascontiguousarray(audio.astype(np.float32))).unsqueeze(0)
        # Move to same device as the pipeline if possible
        try:
            if self._device == "cuda" and torch.cuda.is_available():
                waveform = waveform.to("cuda")
        except Exception:
            pass

        kwargs = {}
        if min_speakers is not None:
            kwargs["min_speakers"] = int(min_speakers)
        if max_speakers is not None:
            kwargs["max_speakers"] = int(max_speakers)

        diarization = self._pipeline(
            {"waveform": waveform, "sample_rate": sample_rate},
            **kwargs,
        )

        out: list[tuple[float, float, str]] = []
        for turn, _track, speaker in diarization.itertracks(yield_label=True):
            out.append((float(turn.start), float(turn.end), str(speaker)))
        return out


def is_available(hf_token: Optional[str] = None) -> tuple[bool, str]:
    """Cheap pre-flight: returns (ok, reason) without loading the model."""
    try:
        import pyannote.audio  # noqa: F401
    except Exception as exc:
        return False, f"pyannote.audio not installed ({exc})"
    if not (hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")):
        return False, "no HuggingFace token configured"
    return True, "ready"
