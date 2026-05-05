from __future__ import annotations

import gc
import threading
from typing import Optional

import numpy as np

from .base import OnDeltaFn, TranscriberEngine

PARAKEET_MODEL_ID = "nvidia/parakeet-tdt-0.6b-v3"


class ParakeetEngine(TranscriberEngine):
    """NVIDIA NeMo Parakeet TDT v3 multilingual ASR backend.

    Loads the model lazily on first use. Streaming is currently implemented as
    repeated buffered transcription (NeMo cache-aware streaming requires the
    chunked encoder; this incremental form works for our short dictation
    sessions and avoids the heavier streaming wiring).
    """

    name = "parakeet-v3"
    display_name = "Parakeet v3 Multilingual"
    approx_vram_gb = 2.0
    speed_x_realtime = 300

    def __init__(self, model_id: str = PARAKEET_MODEL_ID):
        self.model_id = model_id
        self._model = None
        self._lock = threading.Lock()
        self._stream_audio: list[np.ndarray] = []
        self._stream_emitted: str = ""
        self._stream_lang: str = "pt"
        self._stream_on_delta: Optional[OnDeltaFn] = None
        self._stream_min_seconds = 1.5

    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from nemo.collections.asr.models import ASRModel
        except ImportError as e:
            raise RuntimeError(
                "Parakeet requires the 'nemo_toolkit[asr]' package. "
                "Install it with: pip install nemo_toolkit[asr]"
            ) from e

        with self._lock:
            self._model = ASRModel.from_pretrained(self.model_id)
            try:
                import torch

                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                self._model.eval()
            except Exception:
                pass

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

    def _set_language(self, language: str) -> None:
        # Parakeet v3 multilingual: pass `source_lang` ISO 639-1 to transcribe().
        # 'auto' / multilingual: omit so the model decides.
        try:
            self._model.cur_decoder = "rnnt"
        except Exception:
            pass
        from .language import resolve

        whisper_lang, _ = resolve(language)
        if not whisper_lang:
            self._lang_kwarg = {}
        else:
            self._lang_kwarg = {"source_lang": whisper_lang}

    def transcribe_full(self, audio: np.ndarray, language: str = "pt") -> str:
        if self._model is None:
            self.load()
        if audio.size == 0:
            return ""
        self._set_language(language)
        audio = np.ascontiguousarray(audio.astype(np.float32))

        try:
            outputs = self._model.transcribe(
                [audio],
                batch_size=1,
                **self._lang_kwarg,
            )
        except TypeError:
            outputs = self._model.transcribe([audio], batch_size=1)
        except Exception:
            return ""

        text = self._extract_text(outputs)
        return text.strip()

    @staticmethod
    def _extract_text(outputs) -> str:
        if not outputs:
            return ""
        first = outputs[0]
        if isinstance(first, str):
            return first
        if isinstance(first, (list, tuple)) and first:
            inner = first[0]
            if isinstance(inner, str):
                return inner
            return getattr(inner, "text", "") or ""
        return getattr(first, "text", "") or ""

    # ---- Streaming (incremental rewrite of full buffer) ----
    def start_stream(self, language: str = "pt", on_delta: Optional[OnDeltaFn] = None) -> None:
        super().start_stream(language=language, on_delta=on_delta)
        self._stream_audio = []
        self._stream_emitted = ""
        self._stream_lang = language
        self._stream_on_delta = on_delta
        if self._model is None:
            self.load()
        self._set_language(language)

    def push_chunk(self, samples: np.ndarray) -> None:
        self._stream_audio.append(samples.astype(np.float32))
        total = sum(c.size for c in self._stream_audio)
        if total >= int(self._stream_min_seconds * 16000):
            self._maybe_emit_partial()

    def _maybe_emit_partial(self) -> None:
        if self._model is None:
            return
        audio = np.concatenate(self._stream_audio)
        try:
            outputs = self._model.transcribe([audio], batch_size=1, **getattr(self, "_lang_kwarg", {}))
        except TypeError:
            try:
                outputs = self._model.transcribe([audio], batch_size=1)
            except Exception:
                return
        except Exception:
            return

        text = self._extract_text(outputs).strip()
        if text and text != self._stream_emitted:
            if text.startswith(self._stream_emitted):
                delta = text[len(self._stream_emitted):]
            else:
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
        text = self.transcribe_full(audio, language=self._stream_lang)

        delta = ""
        if text.startswith(self._stream_emitted):
            delta = text[len(self._stream_emitted):]
        elif len(text) > len(self._stream_emitted):
            delta = text[len(self._stream_emitted):]
        if delta and self._stream_on_delta:
            try:
                self._stream_on_delta(delta)
            except Exception:
                pass

        self._stream_audio = []
        self._stream_emitted = ""
        return text
