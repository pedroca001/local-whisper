"""Unit tests for the Unicode injector — verifies INPUT struct layout for accents/emoji."""
import sys
import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

from localwhisper.injector import _make_unicode_input, INPUT, KEYBDINPUT, KEYEVENTF_UNICODE, KEYEVENTF_KEYUP


def _utf16_units(s: str) -> list[int]:
    enc = s.encode("utf-16-le")
    return [int.from_bytes(enc[i : i + 2], "little") for i in range(0, len(enc), 2)]


def test_simple_ascii_codepoint():
    units = _utf16_units("a")
    assert units == [ord("a")]
    inp = _make_unicode_input(units[0])
    assert inp.ki.wScan == ord("a")
    assert inp.ki.dwFlags & KEYEVENTF_UNICODE


def test_portuguese_accent():
    """Test that ç, ã and é are emitted as single BMP code units."""
    for ch in ["ç", "ã", "é", "õ"]:
        units = _utf16_units(ch)
        assert len(units) == 1, f"Expected single BMP code unit for {ch!r}"
        inp = _make_unicode_input(units[0], key_up=True)
        assert inp.ki.wScan == ord(ch)
        assert inp.ki.dwFlags & KEYEVENTF_UNICODE
        assert inp.ki.dwFlags & KEYEVENTF_KEYUP


def test_emoji_surrogate_pair():
    units = _utf16_units("🎙")
    assert len(units) == 2
    assert 0xD800 <= units[0] <= 0xDBFF
    assert 0xDC00 <= units[1] <= 0xDFFF
