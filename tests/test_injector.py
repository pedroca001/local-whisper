"""Unit tests for the Unicode injector — verifies INPUT struct layout for accents/emoji."""
import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

from localwhisper.injector import (
    CF_BITMAP,
    CF_DIB,
    CF_DIBV5,
    CF_ENHMETAFILE,
    CF_PALETTE,
    CF_UNICODETEXT,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    VK_CONTROL,
    VK_RETURN,
    VK_V,
    _clipboard_format_uses_hglobal,
    _dword_clipboard_bytes,
    _make_unicode_input,
    _make_vk_input,
    _text_to_clipboard_bytes,
    can_replace_selection_with_message,
    replace_selection_with_message,
)


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


def test_ctrl_v_virtual_key_input():
    down = _make_vk_input(VK_CONTROL)
    up = _make_vk_input(VK_V, key_up=True)
    assert down.ki.wVk == VK_CONTROL
    assert down.ki.dwFlags == 0
    assert up.ki.wVk == VK_V
    assert up.ki.dwFlags & KEYEVENTF_KEYUP


def test_enter_virtual_key_is_available_for_auto_send():
    down = _make_vk_input(VK_RETURN)
    up = _make_vk_input(VK_RETURN, key_up=True)
    assert down.ki.wVk == VK_RETURN
    assert up.ki.dwFlags & KEYEVENTF_KEYUP


def test_protected_clipboard_payload_helpers():
    assert CF_UNICODETEXT == 13
    assert _text_to_clipboard_bytes("abc") == b"a\x00b\x00c\x00\x00\x00"
    assert _dword_clipboard_bytes(0) == b"\x00\x00\x00\x00"


def test_clipboard_snapshot_only_reads_global_memory_formats():
    """GDI clipboard handles must never be passed to GlobalSize/GlobalLock."""
    assert _clipboard_format_uses_hglobal(CF_UNICODETEXT)
    assert _clipboard_format_uses_hglobal(CF_DIB)
    assert _clipboard_format_uses_hglobal(CF_DIBV5)
    assert not _clipboard_format_uses_hglobal(CF_BITMAP)
    assert not _clipboard_format_uses_hglobal(CF_PALETTE)
    assert not _clipboard_format_uses_hglobal(CF_ENHMETAFILE)


def test_win32_message_helpers_reject_missing_hwnd():
    assert not can_replace_selection_with_message(0)
    assert not replace_selection_with_message(0, "hello")
