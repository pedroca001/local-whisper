from __future__ import annotations

import numpy as np

from localwhisper.transcriber.faster_whisper_engine import FasterWhisperEngine
from localwhisper.transcriber.parakeet_engine import ParakeetEngine


class _Segment:
    def __init__(self, text: str):
        self.text = text


class _Info:
    language = "en"
    language_probability = 1.0


class _Model:
    def __init__(self, candidates: list[str]):
        self.candidates = iter(candidates)

    def transcribe(self, _audio, **_kwargs):
        return iter([_Segment(next(self.candidates))]), _Info()


def test_streaming_commits_only_consensus_prefix():
    emitted: list[str] = []
    engine = FasterWhisperEngine()
    engine._model = _Model([
        " hello worl",
        " hello world today",
        " hello world today again",
    ])
    engine._stream_audio = [np.ones(32000, dtype=np.float32) * 0.1]
    engine._stream_whisper_lang = "en"
    engine._stream_vad_filter = False
    engine._stream_prompt = None
    engine._stream_vocabulary = []
    engine._stream_on_delta = emitted.append

    engine._maybe_emit_partial()
    assert emitted == []
    engine._maybe_emit_partial()
    assert "".join(emitted).strip() == "hello"
    engine._maybe_emit_partial()
    assert "".join(emitted).strip() == "hello world"


def test_streaming_partial_inference_is_throttled(monkeypatch):
    engine = FasterWhisperEngine()
    calls: list[int] = []
    monkeypatch.setattr(engine, "_maybe_emit_partial", lambda: calls.append(1))

    block = np.zeros(480, dtype=np.float32)
    for _ in range(100):
        engine.push_chunk(block)

    assert len(calls) == 1


def test_parakeet_partial_inference_is_throttled(monkeypatch):
    engine = ParakeetEngine()
    calls: list[int] = []
    monkeypatch.setattr(engine, "_maybe_emit_partial", lambda: calls.append(1))

    block = np.zeros(480, dtype=np.float32)
    for _ in range(100):
        engine.push_chunk(block)

    assert len(calls) == 1
