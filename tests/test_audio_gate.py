import numpy as np

from localwhisper.audio_gate import analyze_audio_activity, looks_like_silence


def test_empty_audio_is_silence():
    assert looks_like_silence(np.zeros(0, dtype=np.float32))


def test_low_noise_is_silence():
    audio = np.full(16000, 0.0005, dtype=np.float32)
    activity = analyze_audio_activity(audio)
    assert not activity.has_voice
    assert looks_like_silence(audio)


def test_clear_audio_is_voice():
    t = np.linspace(0, 1, 16000, endpoint=False, dtype=np.float32)
    audio = (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    assert analyze_audio_activity(audio).has_voice
    assert not looks_like_silence(audio)
