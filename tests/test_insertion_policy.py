from localwhisper.insertion_policy import input_events_succeeded, target_prefers_clipboard


def test_browser_and_editor_targets_prefer_clipboard():
    assert target_prefers_clipboard("chrome.exe", "New post")
    assert target_prefers_clipboard("Code.exe", "README.md")
    assert target_prefers_clipboard("unknown.exe", "Windows Terminal")


def test_regular_native_targets_do_not_force_clipboard():
    assert not target_prefers_clipboard("notepad.exe", "Untitled - Notepad")
    assert not target_prefers_clipboard("", "")


def test_sendinput_success_thresholds_distinguish_typing_and_paste():
    assert input_events_succeeded(1, via_clipboard=False)
    assert not input_events_succeeded(0, via_clipboard=False)
    assert input_events_succeeded(4, via_clipboard=True)
    assert not input_events_succeeded(3, via_clipboard=True)
