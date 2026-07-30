from __future__ import annotations

import gc
import threading
from typing import Optional

import numpy as np

from ..audio_gate import looks_like_silence
from ..vocabulary import apply_replacements
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
        self._stream_candidate: str = ""
        self._stream_sample_count = 0
        self._stream_last_partial_samples = 0
        self.stream_needs_recovery = False
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

    def transcribe_full(
        self,
        audio: np.ndarray,
        language: str = "pt",
        vad_filter: bool | None = None,
        vocabulary: list[str] | None = None,
    ) -> str:
        if self._model is None:
            self.load()
        if audio.size == 0 or looks_like_silence(audio):
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
        return apply_replacements(text.strip(), None, vocabulary)

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
    def start_stream(
        self,
        language: str = "pt",
        on_delta: Optional[OnDeltaFn] = None,
        vad_filter: bool | None = None,
        vocabulary: list[str] | None = None,
    ) -> None:
        super().start_stream(language=language, on_delta=on_delta, vad_filter=vad_filter, vocabulary=vocabulary)
        self._stream_audio = []
        self._stream_emitted = ""
        self._stream_candidate = ""
        self._stream_sample_count = 0
        self._stream_last_partial_samples = 0
        self.stream_needs_recovery = False
        self._stream_lang = language
        self._stream_on_delta = on_delta
        if self._model is None:
            self.load()
        self._set_language(language)

    def push_chunk(self, samples: np.ndarray) -> None:
        chunk = samples.astype(np.float32)
        self._stream_audio.append(chunk)
        self._stream_sample_count += chunk.size
        elapsed_seconds = self._stream_sample_count / 16000.0
        interval_seconds = min(5.0, self._stream_min_seconds + elapsed_seconds / 60.0)
        interval_samples = int(interval_seconds * 16000)
        if self._stream_sample_count - self._stream_last_partial_samples >= interval_samples:
            self._stream_last_partial_samples = self._stream_sample_count
            self._maybe_emit_partial()

    def _maybe_emit_partial(self) -> None:
        if self._model is None:
            return
        audio = np.concatenate(self._stream_audio)
        if looks_like_silence(audio):
            return
        try:
            outputs = self._model.transcribe([audio], batch_size=1, **getattr(self, "_lang_kwarg", {}))
        except TypeError:
            try:
                outputs = self._model.transcribe([audio], batch_size=1)
            except Exception:
                return
        except Exception:
            return

        text = apply_replacements(self._extract_text(outputs).strip(), None, getattr(self, "_stream_vocabulary", []))
        if text:
            stable = ""
            if self._stream_candidate:
                common_length = 0
                for left, right in zip(self._stream_candidate, text):
                    if left != right:
                        break
                    common_length += 1
                stable = text[:common_length]
                if stable and len(stable) < len(text) and not stable[-1].isspace():
                    stable = stable.rsplit(" ", 1)[0] if " " in stable else ""
            self._stream_candidate = text
            delta = (
                stable[len(self._stream_emitted):]
                if stable.startswith(self._stream_emitted)
                else ""
            )
            if delta and self._stream_on_delta:
                try:
                    self._stream_on_delta(delta)
                except Exception:
                    pass
            if stable:
                self._stream_emitted = stable

    def finalize_stream(self) -> str:
        if not self._stream_audio:
            return self._stream_emitted
        audio = np.concatenate(self._stream_audio)
        if looks_like_silence(audio):
            self._stream_audio = []
            self._stream_emitted = ""
            self._stream_candidate = ""
            self._stream_sample_count = 0
            self._stream_last_partial_samples = 0
            return ""
        text = self.transcribe_full(audio, language=self._stream_lang)

        delta = ""
        if text.startswith(self._stream_emitted):
            delta = text[len(self._stream_emitted):]
        elif self._stream_emitted:
            self.stream_needs_recovery = True
        if delta and self._stream_on_delta:
            try:
                self._stream_on_delta(delta)
            except Exception:
                pass

        self._stream_audio = []
        self._stream_emitted = ""
        self._stream_candidate = ""
        self._stream_sample_count = 0
        self._stream_last_partial_samples = 0
        return text
