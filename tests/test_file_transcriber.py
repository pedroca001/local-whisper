from __future__ import annotations

import numpy as np
import pytest

from localwhisper.transcriber import file_transcriber as ft


class _Engine:
    pass


def test_subtitle_exports_are_timestamped():
    result = ft.FileTranscript(
        segments=[
            ft.TranscriptSegment(0.0, 1.25, "Hello", "Speaker 1"),
            ft.TranscriptSegment(61.5, 62.0, "World", "Speaker 2"),
        ],
        duration_s=62.0,
        diarized=True,
        num_speakers=2,
    )
    assert "00:00:00,000 --> 00:00:01,250" in result.to_srt()
    assert "[Speaker 1] Hello" in result.to_srt()
    assert result.to_vtt().startswith("WEBVTT")
    assert "00:01:01.500 --> 00:01:02.000" in result.to_vtt()


def test_non_diarized_files_are_processed_in_bounded_chunks(monkeypatch):
    chunks = [
        np.ones(16000, dtype=np.float32),
        np.ones(8000, dtype=np.float32),
    ]
    monkeypatch.setattr(ft, "probe_duration", lambda _path: 1.5)
    monkeypatch.setattr(ft, "iter_pcm16k", lambda *_args, **_kwargs: iter(chunks))
    monkeypatch.setattr(
        ft,
        "_transcribe_with_timestamps",
        lambda _engine, audio, language: [
            {"start": 0.0, "end": audio.size / 16000, "text": language}
        ],
    )

    result = ft.transcribe_file(
        "ignored.wav",
        engine=_Engine(),
        language="pt-BR",
        diarize=False,
        chunk_seconds=1,
    )
    assert result.duration_s == 1.5
    assert len(result.segments) == 2
    assert result.segments[1].start == 1.0
    assert result.segments[1].end == 1.5


def test_cancelled_job_stops_before_decode():
    token = ft.CancellationToken()
    token.cancel()
    with pytest.raises(ft.FileTranscriptionCancelled):
        ft.transcribe_file(
            "ignored.wav",
            engine=_Engine(),
            diarize=False,
            cancel_token=token,
        )
