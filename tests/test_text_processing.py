from localwhisper.text_processing import (
    apply_spoken_commands,
    mode_for_target,
    normalize_formatting,
    process_transcript,
    remove_fillers,
)


def test_spoken_commands_support_portuguese_and_english():
    assert apply_spoken_commands("olá nova linha mundo ponto final") == "olá\nmundo."
    assert apply_spoken_commands("hello new paragraph world period") == "hello\n\nworld."


def test_full_processing_cleans_spacing_capitalization_and_fillers():
    result = process_transcript(
        "hum olá vírgula mundo ponto final nova linha tudo bem ponto de interrogação"
    )
    assert result == "Olá, mundo.\nTudo bem?"


def test_remove_fillers_is_conservative():
    assert remove_fillers("hum eu concordo") == "eu concordo"
    assert remove_fillers("este tipo funciona") == "este tipo funciona"
    assert remove_fillers("um projeto importante") == "um projeto importante"


def test_normalize_formatting_does_not_lowercase_existing_content():
    assert normalize_formatting("localWhisper funciona. cuda também") == "LocalWhisper funciona. Cuda também"


def test_app_pattern_mode_wins_over_default():
    modes = [
        {"id": "default", "name": "Natural", "app_patterns": []},
        {"id": "prompt", "name": "Prompt", "app_patterns": ["codex", "code.exe"]},
    ]
    selected = mode_for_target(modes, "default", "Code.exe", "Codex")
    assert selected["id"] == "prompt"
