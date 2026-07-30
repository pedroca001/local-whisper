"""Transcribe arbitrary audio/video files (mp3, mp4, m4a, wav, etc.).

Pipeline:
    1. Decode the file with ffmpeg into a 16 kHz mono float32 numpy array.
    2. (Optional) Run pyannote speaker diarization to get per-speaker segments.
    3. Run the user's chosen ASR engine (Whisper / Parakeet) on the full audio.
    4. Stitch the two together: each ASR word/segment gets the speaker label
       whose diarization turn covers most of its time-range.

The output is always a list of dicts:
    {"start": float seconds,
     "end":   float seconds,
     "speaker": "Speaker 1" | None,
     "text":  str}

Plus convenience formatters: format_txt, format_json.

ffmpeg is required on PATH. faster-whisper bundles it on Windows as a wheel
dependency in some setups, but to keep this module self-contained we shell
out and validate the binary up front.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 16000  # Whisper / pyannote both want 16 kHz mono


def unique_output_paths(
    sources: list[str | Path],
    output_dir: str | Path,
    suffix: str,
) -> list[Path]:
    """Choose stable batch destinations without overwriting existing files."""
    folder = Path(output_dir)
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    reserved = {
        path.name.casefold()
        for path in folder.iterdir()
        if path.is_file()
    } if folder.is_dir() else set()
    destinations: list[Path] = []
    for source in sources:
        stem = Path(source).stem
        sequence = 1
        while True:
            postfix = "" if sequence == 1 else f"-{sequence}"
            name = f"{stem}{postfix}{normalized_suffix}"
            if name.casefold() not in reserved:
                reserved.add(name.casefold())
                destinations.append(folder / name)
                break
            sequence += 1
    return destinations


# ─── ffmpeg discovery ──────────────────────────────────────────────────────
def _ffmpeg_path() -> str | None:
    """Return path to ffmpeg, searching PATH first, then a few well-known places."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    if sys.platform == "win32":
        # imageio-ffmpeg ships an ffmpeg.exe — many Whisper setups already pull it in
        try:
            import imageio_ffmpeg  # type: ignore
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and Path(exe).exists():
                return exe
        except Exception:
            pass
    return None


class FFmpegMissingError(RuntimeError):
    pass


class FileTranscriptionCancelled(RuntimeError):
    pass


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise FileTranscriptionCancelled("Transcription cancelled.")


def probe_duration(path: str | os.PathLike) -> float | None:
    """Read media duration from ffmpeg metadata without decoding the file."""
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return None
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-i", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
        creationflags=creationflags,
    )
    match = re.search(
        rb"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        proc.stderr or b"",
    )
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def iter_pcm16k(
    path: str | os.PathLike,
    *,
    chunk_seconds: float = 30.0,
    cancel_token: CancellationToken | None = None,
):
    """Yield bounded mono float32 chunks decoded by one ffmpeg process."""
    src = str(path)
    if not Path(src).exists():
        raise FileNotFoundError(src)
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise FFmpegMissingError(
            "ffmpeg was not found on PATH. Install ffmpeg from https://ffmpeg.org "
            "or `pip install imageio-ffmpeg`."
        )
    cmd = [
        ffmpeg,
        "-nostdin",
        "-loglevel", "error",
        "-i", src,
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        "-",
    ]
    logging.info("ffmpeg streaming decode: %s", " ".join(cmd))
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    bytes_per_chunk = max(2, int(chunk_seconds * SAMPLE_RATE) * 2)
    bytes_per_chunk -= bytes_per_chunk % 2
    try:
        assert proc.stdout is not None
        while True:
            if cancel_token:
                cancel_token.raise_if_cancelled()
            raw = proc.stdout.read(bytes_per_chunk)
            if not raw:
                break
            if len(raw) % 2:
                raw = raw[:-1]
            if raw:
                yield np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        stderr = proc.stderr.read() if proc.stderr is not None else b""
        return_code = proc.wait()
        if return_code != 0:
            raise RuntimeError(
                f"ffmpeg failed (code {return_code}): "
                f"{stderr.decode('utf-8', 'replace')[:500]}"
            )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()


def decode_to_pcm16k(
    path: str | os.PathLike,
    *,
    cancel_token: CancellationToken | None = None,
) -> np.ndarray:
    """Decode any audio/video file to mono float32 @ 16 kHz using ffmpeg."""
    chunks = list(iter_pcm16k(path, chunk_seconds=60.0, cancel_token=cancel_token))
    if not chunks:
        raise RuntimeError("ffmpeg produced no audio (file empty or unreadable).")
    return np.concatenate(chunks)


# ─── data structures ───────────────────────────────────────────────────────
@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


@dataclass
class FileTranscript:
    segments: list[TranscriptSegment] = field(default_factory=list)
    language: Optional[str] = None
    num_speakers: int = 0
    duration_s: float = 0.0
    diarized: bool = False

    def to_txt(self, with_timestamps: bool = False) -> str:
        """Render as human-readable plain text with [Speaker N] tags.

        Consecutive segments by the same speaker are merged into a paragraph.
        """
        if not self.segments:
            return ""
        out: list[str] = []
        cur_speaker: Optional[str] = object()  # sentinel
        cur_chunks: list[str] = []
        cur_start: float = 0.0
        cur_end: float = 0.0

        def _flush():
            if not cur_chunks:
                return
            label = cur_speaker or "Speaker"
            line = " ".join(s.strip() for s in cur_chunks if s.strip())
            if not line:
                return
            if with_timestamps:
                out.append(f"[{_fmt_ts(cur_start)} → {_fmt_ts(cur_end)}] [{label}] {line}")
            else:
                out.append(f"[{label}] {line}")

        for seg in self.segments:
            if seg.speaker != cur_speaker:
                _flush()
                cur_chunks = []
                cur_speaker = seg.speaker
                cur_start = seg.start
            cur_end = seg.end
            cur_chunks.append(seg.text)
        _flush()
        return "\n\n".join(out)

    def to_json(self) -> str:
        return json.dumps(
            {
                "language": self.language,
                "num_speakers": self.num_speakers,
                "duration_s": self.duration_s,
                "diarized": self.diarized,
                "segments": [
                    {"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text}
                    for s in self.segments
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    def to_srt(self) -> str:
        blocks = []
        for index, segment in enumerate(self.segments, 1):
            label = f"[{segment.speaker}] " if segment.speaker else ""
            blocks.append(
                f"{index}\n{_fmt_subtitle_ts(segment.start, srt=True)} --> "
                f"{_fmt_subtitle_ts(segment.end, srt=True)}\n"
                f"{label}{segment.text.strip()}"
            )
        return "\n\n".join(blocks).strip() + ("\n" if blocks else "")

    def to_vtt(self) -> str:
        blocks = ["WEBVTT", ""]
        for segment in self.segments:
            label = f"<v {segment.speaker}>" if segment.speaker else ""
            blocks.append(
                f"{_fmt_subtitle_ts(segment.start, srt=False)} --> "
                f"{_fmt_subtitle_ts(segment.end, srt=False)}\n"
                f"{label}{segment.text.strip()}"
            )
        return "\n\n".join(blocks).rstrip() + "\n"


def _fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"


def _fmt_subtitle_ts(value: float, *, srt: bool) -> str:
    milliseconds = max(0, int(round(value * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


# ─── speaker stitching ─────────────────────────────────────────────────────
def _assign_speaker(seg_start: float, seg_end: float, turns: list[tuple[float, float, str]]) -> Optional[str]:
    """Pick the speaker whose diarization turn overlaps `seg` the most."""
    if not turns:
        return None
    best_overlap = 0.0
    best_speaker: Optional[str] = None
    for ts, te, sp in turns:
        overlap = max(0.0, min(te, seg_end) - max(ts, seg_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = sp
    # If there's no overlap at all, fall back to the closest turn's speaker.
    if best_speaker is None:
        center = (seg_start + seg_end) / 2.0
        best_dist = float("inf")
        for ts, te, sp in turns:
            dist = 0.0 if ts <= center <= te else min(abs(center - ts), abs(center - te))
            if dist < best_dist:
                best_dist = dist
                best_speaker = sp
    return best_speaker


def _normalize_speaker_labels(turns: list[tuple[float, float, str]]) -> tuple[list[tuple[float, float, str]], dict[str, str]]:
    """Map raw pyannote labels (SPEAKER_00, SPEAKER_01, ...) to 'Speaker 1', 'Speaker 2', ...

    Order of first appearance determines numbering.
    """
    mapping: dict[str, str] = {}
    next_id = 1
    out: list[tuple[float, float, str]] = []
    for ts, te, raw in sorted(turns, key=lambda t: t[0]):
        if raw not in mapping:
            mapping[raw] = f"Speaker {next_id}"
            next_id += 1
        out.append((ts, te, mapping[raw]))
    return out, mapping


# ─── orchestrator ──────────────────────────────────────────────────────────
ProgressFn = Callable[[str, float], None]
"""Callback: (stage_label, progress_0_to_1). progress < 0 means indeterminate."""


def transcribe_file(
    path: str | os.PathLike,
    *,
    engine,                              # TranscriberEngine (already loaded preferably)
    language: str = "auto",
    diarize: bool = True,
    hf_token: Optional[str] = None,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    on_progress: Optional[ProgressFn] = None,
    cancel_token: CancellationToken | None = None,
    chunk_seconds: float = 30.0,
) -> FileTranscript:
    """High-level entry point used by the UI page.

    Stages:
        1. decode (ffmpeg)
        2. diarize (pyannote, optional)
        3. transcribe (whisper segments with timestamps)
        4. stitch (assign speaker per ASR segment)
    """
    def _progress(label: str, pct: float = -1.0) -> None:
        logging.info("[file_transcribe] %s (%.0f%%)", label, max(pct, 0) * 100)
        if on_progress:
            try:
                on_progress(label, pct)
            except Exception:
                pass

    token = cancel_token or CancellationToken()
    token.raise_if_cancelled()
    duration_hint = probe_duration(path)

    # ─ diarization (optional, can be slow) ──────────────────────────────
    raw_turns: list[tuple[float, float, str]] = []
    diarized = False
    if diarize:
        _progress("Decoding audio for speaker identification…", 0.0)
        audio = decode_to_pcm16k(path, cancel_token=token)
        duration = audio.size / SAMPLE_RATE
        _progress(f"Decoded {duration:.1f}s of audio", 0.10)
        try:
            from .diarization import DiarizationPipeline

            _progress("Loading speaker diarization model…", 0.15)
            pipeline = DiarizationPipeline(hf_token=hf_token)
            pipeline.load()
            token.raise_if_cancelled()
            _progress("Identifying speakers (this can take a while)…", 0.20)
            raw_turns = pipeline.diarize(
                audio,
                sample_rate=SAMPLE_RATE,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
            diarized = True
            token.raise_if_cancelled()
            _progress(f"Found {len({s for *_, s in raw_turns})} speaker(s)", 0.55)
        except FileTranscriptionCancelled:
            raise
        except Exception as exc:
            logging.exception("Diarization failed; continuing without speaker labels")
            _progress(f"Diarization unavailable ({exc}). Continuing without speakers…", 0.55)
            raw_turns = []
            diarized = False
        turns, _label_map = _normalize_speaker_labels(raw_turns)
        _progress("Transcribing audio…", 0.60)
        token.raise_if_cancelled()
        asr_segments = _transcribe_with_timestamps(engine, audio, language=language)
    else:
        turns = []
        asr_segments = []
        processed = 0.0
        duration = float(duration_hint or 0.0)
        _progress("Streaming audio into the speech model…", 0.05)
        for chunk in iter_pcm16k(
            path,
            chunk_seconds=chunk_seconds,
            cancel_token=token,
        ):
            token.raise_if_cancelled()
            chunk_duration = chunk.size / SAMPLE_RATE
            for segment in _transcribe_with_timestamps(engine, chunk, language=language):
                asr_segments.append(
                    {
                        "start": float(segment["start"]) + processed,
                        "end": float(segment["end"]) + processed,
                        "text": segment["text"],
                    }
                )
            processed += chunk_duration
            duration = max(duration, processed)
            pct = min(0.94, 0.05 + (processed / duration_hint) * 0.89) if duration_hint else -1.0
            _progress(f"Transcribed {processed / 60:.1f} min", pct)
        token.raise_if_cancelled()

    _progress("Stitching speakers and text…", 0.95)

    # ─ stitch ───────────────────────────────────────────────────────────
    out_segments: list[TranscriptSegment] = []
    for s in asr_segments:
        sp = _assign_speaker(s["start"], s["end"], turns) if turns else None
        out_segments.append(
            TranscriptSegment(
                start=float(s["start"]),
                end=float(s["end"]),
                text=str(s["text"]).strip(),
                speaker=sp,
            )
        )

    num_speakers = len({s.speaker for s in out_segments if s.speaker}) if turns else 0
    result = FileTranscript(
        segments=out_segments,
        language=language if language != "auto" else None,
        num_speakers=num_speakers,
        duration_s=duration,
        diarized=diarized,
    )
    _progress("Done", 1.0)
    return result


def _transcribe_with_timestamps(engine, audio: np.ndarray, language: str) -> list[dict]:
    """Run ASR and return [{start, end, text}, …].

    Tries to use faster-whisper's native segment timestamps when available
    (i.e., engine wraps a faster-whisper WhisperModel). Falls back to a
    single segment covering the whole file for engines that only expose
    transcribe_full().
    """
    # Best path: pull the underlying faster-whisper model directly.
    fw_model = getattr(engine, "_model", None)
    if fw_model is not None and hasattr(fw_model, "transcribe"):
        from .language import resolve as _resolve_lang

        whisper_lang, initial_prompt = _resolve_lang(language)
        kwargs = {
            "language": whisper_lang,
            "beam_size": 5,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
            "word_timestamps": False,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        try:
            audio = np.ascontiguousarray(audio.astype(np.float32))
            segments, _info = fw_model.transcribe(audio, **kwargs)
            out = []
            for seg in segments:
                out.append({
                    "start": float(getattr(seg, "start", 0.0) or 0.0),
                    "end": float(getattr(seg, "end", 0.0) or 0.0),
                    "text": getattr(seg, "text", "") or "",
                })
            return out
        except Exception:
            logging.exception("faster-whisper segment-level transcribe failed; falling back")

    # Fallback: full transcript as a single segment.
    text = engine.transcribe_full(audio, language=language)
    return [{"start": 0.0, "end": audio.size / SAMPLE_RATE, "text": text}]
