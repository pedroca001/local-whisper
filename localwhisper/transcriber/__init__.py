from .base import TranscriberEngine
from .registry import MODELS, get_engine, list_models

__all__ = [
    "TranscriberEngine",
    "MODELS",
    "get_engine",
    "list_models",
    "transcribe_file",
    "FileTranscript",
    "TranscriptSegment",
]


def __getattr__(name):
    # Lazy re-exports so importing `localwhisper.transcriber` doesn't pull in
    # ffmpeg/pyannote at startup.
    if name in ("transcribe_file", "FileTranscript", "TranscriptSegment"):
        from .file_transcriber import (
            FileTranscript,
            TranscriptSegment,
            transcribe_file,
        )
        return locals()[name]
    raise AttributeError(name)
