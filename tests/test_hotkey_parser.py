import sys
import pytest

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

from localwhisper.hotkey import parse_hotkey, MOD_CONTROL, MOD_ALT, MOD_SHIFT, MOD_NOREPEAT, VK_CODES


def test_ctrl_space():
    mods, vk = parse_hotkey("ctrl+space")
    assert mods & MOD_CONTROL
    assert mods & MOD_NOREPEAT
    assert vk == VK_CODES["space"]


def test_ctrl_alt_space():
    mods, vk = parse_hotkey("ctrl+alt+space")
    assert mods & MOD_CONTROL
    assert mods & MOD_ALT
    assert vk == 0x20


def test_f8():
    mods, vk = parse_hotkey("f8")
    assert vk == VK_CODES["f8"]


def test_invalid_only_modifier():
    with pytest.raises(ValueError):
        parse_hotkey("ctrl")
