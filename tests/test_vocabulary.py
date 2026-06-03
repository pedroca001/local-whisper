from localwhisper.vocabulary import apply_replacements


def test_configured_replacement_is_case_insensitive():
    text = apply_replacements("abre o cloud agora", [{"from": "cloud", "to": "CLAUDE"}])
    assert text == "abre o CLAUDE agora"


def test_claude_vocabulary_adds_default_cloud_correction():
    text = apply_replacements("usa o cloud.md", [], ["CLAUDE.md"])
    assert text == "usa o CLAUDE.md"


def test_replacement_respects_word_boundaries():
    text = apply_replacements("cloud cloudflare", [{"from": "cloud", "to": "CLAUDE"}])
    assert text == "CLAUDE cloudflare"
