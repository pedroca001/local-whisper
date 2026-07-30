from __future__ import annotations

from localwhisper import insertion_policy, text_processing


def test_profile_output_can_inherit_or_override_global_default() -> None:
    assert (
        text_processing.resolve_output_action(
            {"output_action": "default"},
            "clipboard",
        )
        == "clipboard"
    )
    assert (
        text_processing.resolve_output_action(
            {"output_action": "history"},
            "clipboard",
        )
        == "history"
    )


def test_streaming_only_injects_for_inserting_output_actions() -> None:
    assert text_processing.output_action_allows_insertion("insert")
    assert text_processing.output_action_allows_insertion("insert_enter")
    assert not text_processing.output_action_allows_insertion("clipboard")
    assert not text_processing.output_action_allows_insertion("history")


def test_streaming_non_inserting_or_recovery_output_gets_full_processing() -> None:
    assert text_processing.should_process_final_transcript(
        streaming=True,
        output_action="clipboard",
        needs_recovery=False,
    )
    assert text_processing.should_process_final_transcript(
        streaming=True,
        output_action="history",
        needs_recovery=False,
    )
    assert text_processing.should_process_final_transcript(
        streaming=True,
        output_action="insert",
        needs_recovery=True,
    )
    assert not text_processing.should_process_final_transcript(
        streaming=True,
        output_action="insert",
        needs_recovery=False,
    )


def test_enter_is_never_submitted_for_a_recovery_result() -> None:
    assert text_processing.should_submit_enter(
        output_action="insert_enter",
        can_inject=True,
        injected=True,
        needs_recovery=False,
    )
    assert not text_processing.should_submit_enter(
        output_action="insert_enter",
        can_inject=True,
        injected=True,
        needs_recovery=True,
    )


def test_enter_requires_the_exact_captured_window_to_remain_editable() -> None:
    target = {
        "hwnd": 101,
        "process": "notepad.exe",
        "can_inject": True,
    }
    assert insertion_policy.enter_target_is_still_safe(
        target,
        target_hwnd=101,
        target_app="notepad.exe",
    )
    assert not insertion_policy.enter_target_is_still_safe(
        {**target, "hwnd": 202},
        target_hwnd=101,
        target_app="notepad.exe",
    )
    assert not insertion_policy.enter_target_is_still_safe(
        {**target, "can_inject": False},
        target_hwnd=101,
        target_app="notepad.exe",
    )
