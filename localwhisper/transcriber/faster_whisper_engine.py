from __future__ import annotations

import gc
import logging
import threading
from typing import Optional

import numpy as np

from ..config import MODELS_DIR
from ..audio_gate import looks_like_silence
from ..vocabulary import apply_replacements
from .base import OnDeltaFn, TranscriberEngine


class FasterWhisperEngine(TranscriberEngine):
    """faster-whisper (CTranslate2) backend for large-v3-turbo and large-v3."""

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        compute_type: str = "float16",
        compute_device: str = "auto",
        models_dir: str | None = None,
    ):
        self.model_name = model_name
        self.compute_type = compute_type
        self.compute_device = compute_device if compute_device in ("auto", "cuda", "cpu") else "auto"
        self.models_dir = models_dir or str(MODELS_DIR)
        self._model = None
        self._lock = threading.Lock()

        if model_name == "large-v3-turbo":
            self.name = "whisper-turbo"
            self.display_name = "Whisper Turbo (large-v3-turbo)"
            self.approx_vram_gb = 3.0
            self.speed_x_realtime = 100
        else:
            self.name = "whisper-ultra"
            self.display_name = "Whisper Ultra (large-v3)"
            self.approx_vram_gb = 5.0
            self.speed_x_realtime = 50

        # Streaming state
        self._stream_audio: list[np.ndarray] = []
        self._stream_emitted: str = ""
        self._stream_lang: str = "pt"
        self._stream_on_delta: Optional[OnDeltaFn] = None
        self._stream_vad_filter: bool | None = None
        self._stream_vocabulary: list[str] = []
        self._stream_min_seconds = 1.5  # transcribe every ~1.5s of accumulated audio
        self._device = "unknown"

    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        if self.compute_device != "cpu" and self._cuda_runtime_available():
            try:
                with self._lock:
                    self._model = WhisperModel(
                        self.model_name,
                        device="cuda",
                        compute_type=self.compute_type,
                        download_root=self.models_dir,
                    )
                    self._device = "cuda"
                # Force CUDA lazy-init NOW — ctranslate2 only loads cuBLAS on the
                # first actual inference call, not at model construction time.
                # Running a tiny warm-up here ensures any DLL-not-found errors are
                # caught while we still have the CPU fallback available.
                _dummy = np.zeros(8000, dtype=np.float32)
                _segs, _ = self._model.transcribe(_dummy, language="en", vad_filter=False)
                list(_segs)  # consume the generator to trigger execution
                logging.info("WhisperModel loaded on CUDA with compute_type=%s (warm-up OK)", self.compute_type)
                return
            except Exception:
                logging.exception("CUDA WhisperModel failed (load or warm-up); falling back to CPU")
                self._model = None
                self._device = "unknown"
        elif self.compute_device == "cuda":
            logging.warning("CUDA was requested, but it is not available; falling back to CPU")

        with self._lock:
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
                download_root=self.models_dir,
            )
            self._device = "cpu"
        logging.info("WhisperModel loaded on CPU with compute_type=int8")

    @staticmethod
    def _language_name(info) -> str:
        return (getattr(info, "language", "") or "").lower()

    @staticmethod
    def _language_probability(info) -> float:
        try:
            return float(getattr(info, "language_probability", 0.0) or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _looks_like_bad_short_auto(language: str, probability: float, audio: np.ndarray) -> bool:
        duration_s = audio.size / 16000.0
        if duration_s > 8.0:
            return False
        # Short Brazilian Portuguese dictations often get mislabeled as Spanish
        # or French. Keep genuine English/multilingual use, but retry weak
        # Romance-language guesses with an explicit Portuguese bias.
        return language in {"es", "fr", "it"} and probability < 0.85

    @staticmethod
    def _prompt_with_vocabulary(prompt: str | None, vocabulary: list[str] | None) -> str | None:
        words = [w.strip() for w in (vocabulary or []) if w and w.strip()]
        if not words:
            return prompt
        vocab_prompt = "Vocabulário personalizado: " + ", ".join(words[:120]) + "."
        return f"{prompt} {vocab_prompt}" if prompt else vocab_prompt

    @staticmethod
    def _cuda_runtime_available() -> bool:
        """Return True when a CUDA-capable device is accessible via ctranslate2.

        gpu.setup() must have been called at app startup so that the CUDA Toolkit
        bin directory is already registered via os.add_dll_directory() before
        ctranslate2 tries to load cuBLAS.
        """
        try:
            import ctranslate2
            return ctranslate2.get_cuda_device_count() > 0
        except Exception as exc:
            logging.info("CUDA not available: %s", exc)
            return False

    def unload(self) -> None:
        with self._lock:
            self._model = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def _use_vad(audio: np.ndarray, vad_filter: bool | None) -> bool:
        duration_s = audio.size / 16000.0
        if vad_filter is None:
            return duration_s >= 3.0
        return bool(vad_filter) and duration_s >= 3.0

    def transcribe_full(
        self,
        audio: np.ndarray,
        language: str = "pt-BR",
        vad_filter: bool | None = None,
        vocabulary: list[str] | None = None,
    ) -> str:
        if self._model is None:
            self.load()
        audio = np.ascontiguousarray(audio.astype(np.float32))
        if audio.size == 0 or looks_like_silence(audio):
            return ""
        from .language import resolve

        whisper_lang, initial_prompt = resolve(language)
        kwargs = {
            "language": whisper_lang,
            "beam_size": 5,
            "vad_filter": self._use_vad(audio, vad_filter),
            "vad_parameters": {"min_silence_duration_ms": 700},
        }
        logging.info(
            "Transcribing audio: duration=%.2fs language=%s whisper_language=%s vad_filter=%s",
            audio.size / 16000.0,
            language,
            whisper_lang or "auto",
            kwargs["vad_filter"],
        )
        if initial_prompt:
            kwargs["initial_prompt"] = self._prompt_with_vocabulary(initial_prompt, vocabulary)
        elif vocabulary:
            kwargs["initial_prompt"] = self._prompt_with_vocabulary(None, vocabulary)
        try:
            segments, info = self._model.transcribe(audio, **kwargs)
        except RuntimeError as exc:
            msg = str(exc).lower()
            if self._device == "cuda" and ("cublas" in msg or "cuda" in msg or "cudnn" in msg):
                logging.exception("CUDA transcription failed; retrying on CPU")
                self.unload()
                self._model = None
                with self._lock:
                    from faster_whisper import WhisperModel

                    self._model = WhisperModel(
                        self.model_name,
                        device="cpu",
                        compute_type="int8",
                        download_root=self.models_dir,
                    )
                    self._device = "cpu"
                segments, info = self._model.transcribe(audio, **kwargs)
            else:
                raise
        text = "".join(seg.text for seg in segments).strip()
        detected_lang = self._language_name(info)
        detected_prob = self._language_probability(info)
        if whisper_lang is None and self._looks_like_bad_short_auto(detected_lang, detected_prob, audio):
            retry_kwargs = dict(kwargs)
            retry_kwargs["language"] = "pt"
            logging.info(
                "Auto language looked unreliable for short dictation: detected=%s prob=%.2f; retrying as pt-BR",
                detected_lang,
                detected_prob,
            )
            segments, _info = self._model.transcribe(audio, **retry_kwargs)
            retry_text = "".join(seg.text for seg in segments).strip()
            if retry_text:
                text = retry_text
        if not text and kwargs.get("vad_filter") and audio.size > 0:
            retry_kwargs = dict(kwargs)
            retry_kwargs["vad_filter"] = False
            logging.info("VAD produced empty transcription; retrying without VAD")
            segments, _info = self._model.transcribe(audio, **retry_kwargs)
            text = "".join(seg.text for seg in segments).strip()
        return apply_replacements(text, None, vocabulary)

    # ---- Streaming ----
    def start_stream(
        self,
        language: str = "pt-BR",
        on_delta: Optional[OnDeltaFn] = None,
        vad_filter: bool | None = None,
        vocabulary: list[str] | None = None,
    ) -> None:
        super().start_stream(language=language, on_delta=on_delta, vad_filter=vad_filter, vocabulary=vocabulary)
        from .language import resolve

        self._stream_audio = []
        self._stream_emitted = ""
        self._stream_lang = language
        self._stream_vad_filter = vad_filter
        self._stream_vocabulary = vocabulary or []
        self._stream_whisper_lang, self._stream_prompt = resolve(language)
        self._stream_prompt = self._prompt_with_vocabulary(self._stream_prompt, self._stream_vocabulary)
        self._stream_on_delta = on_delta
        if self._model is None:
            self.load()

    def push_chunk(self, samples: np.ndarray) -> None:
        self._stream_audio.append(samples.astype(np.float32))
        total_samples = sum(c.size for c in self._stream_audio)
        if total_samples >= int(self._stream_min_seconds * 16000):
            self._maybe_emit_partial()

    def _maybe_emit_partial(self) -> None:
        if self._model is None:
            return
        audio = np.concatenate(self._stream_audio)
        if looks_like_silence(audio):
            return
        kwargs = {
            "language": self._stream_whisper_lang,
            "beam_size": 1,
            "vad_filter": self._use_vad(audio, self._stream_vad_filter),
            "vad_parameters": {"min_silence_duration_ms": 400},
            "condition_on_previous_text": False,
        }
        if self._stream_prompt:
            kwargs["initial_prompt"] = self._stream_prompt
        try:
            segments, info = self._model.transcribe(audio, **kwargs)
            text = "".join(seg.text for seg in segments).strip()
        except Exception:
            return
        detected_lang = self._language_name(info)
        detected_prob = self._language_probability(info)
        if self._stream_whisper_lang is None and self._looks_like_bad_short_auto(detected_lang, detected_prob, audio):
            retry_kwargs = dict(kwargs)
            retry_kwargs["language"] = "pt"
            try:
                segments, _info = self._model.transcribe(audio, **retry_kwargs)
                retry_text = "".join(seg.text for seg in segments).strip()
                if retry_text:
                    text = retry_text
            except Exception:
                pass

        text = apply_replacements(text, None, self._stream_vocabulary)

        if text and text != self._stream_emitted:
            # Emit only the new suffix
            if text.startswith(self._stream_emitted):
                delta = text[len(self._stream_emitted):]
            else:
                # Heuristic: word overlap recovery — emit the full new tail
                delta = text[len(self._stream_emitted):] if len(text) > len(self._stream_emitted) else ""
            if delta and self._stream_on_delta:
                try:
                    self._stream_on_delta(delta)
                except Exception:
                    pass
            self._stream_emitted = text

    def finalize_stream(self) -> str:
        if not self._stream_audio:
            return self._stream_emitted
        audio = np.concatenate(self._stream_audio)
        if looks_like_silence(audio):
            self._stream_audio = []
            self._stream_emitted = ""
            return ""
        kwargs = {
            "language": self._stream_whisper_lang,
            "beam_size": 5,
            "vad_filter": self._use_vad(audio, self._stream_vad_filter),
            "vad_parameters": {"min_silence_duration_ms": 700},
        }
        if self._stream_prompt:
            kwargs["initial_prompt"] = self._stream_prompt
        try:
            segments, info = self._model.transcribe(audio, **kwargs)
            final = "".join(seg.text for seg in segments).strip()
        except Exception:
            final = self._stream_emitted
        else:
            detected_lang = self._language_name(info)
            detected_prob = self._language_probability(info)
            if self._stream_whisper_lang is None and self._looks_like_bad_short_auto(detected_lang, detected_prob, audio):
                retry_kwargs = dict(kwargs)
                retry_kwargs["language"] = "pt"
                logging.info(
                    "Streaming auto language looked unreliable: detected=%s prob=%.2f; retrying as pt-BR",
                    detected_lang,
                    detected_prob,
                )
                try:
                    segments, _info = self._model.transcribe(audio, **retry_kwargs)
                    retry_final = "".join(seg.text for seg in segments).strip()
                    if retry_final:
                        final = retry_final
                except Exception:
                    pass
        if not final and kwargs.get("vad_filter") and audio.size > 0 and not looks_like_silence(audio):
            retry_kwargs = dict(kwargs)
            retry_kwargs["vad_filter"] = False
            logging.info("Streaming VAD produced empty transcription; retrying without VAD")
            try:
                segments, _info = self._model.transcribe(audio, **retry_kwargs)
                final = "".join(seg.text for seg in segments).strip()
            except Exception:
                final = self._stream_emitted

        delta = ""
        if final.startswith(self._stream_emitted):
            delta = final[len(self._stream_emitted):]
        elif len(final) > len(self._stream_emitted):
            delta = final[len(self._stream_emitted):]
        if delta and self._stream_on_delta:
            try:
                self._stream_on_delta(delta)
            except Exception:
                pass

        self._stream_audio = []
        self._stream_emitted = ""
        return apply_replacements(final, None, self._stream_vocabulary)
