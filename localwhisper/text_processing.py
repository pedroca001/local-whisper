"""Fast, deterministic post-processing for offline dictation.

The transformations are conservative, testable and work without a network
connection or a language model.
"""
from __future__ import annotations

import re
from typing import Iterable

_FILLER_PATTERNS = (
    # "um" is intentionally not removed: in Portuguese it is a common
    # article/number, so treating it as an English hesitation changes meaning.
    r"\b(?:hum+|ahn+|hã+|uh+)\b[,.]?\s*",
    r"\b(?:you know)\b[,.]?\s*",
)

_SPOKEN_COMMANDS: tuple[tuple[str, str], ...] = (
    (r"\b(?:novo par[aá]grafo|new paragraph)\b[,.]?", "\n\n"),
    (r"\b(?:nova linha|new line)\b[,.]?", "\n"),
    (r"\b(?:ponto final|full stop|period)\b", "."),
    (r"\b(?:ponto de interroga[cç][aã]o|question mark)\b", "?"),
    (r"\b(?:ponto de exclama[cç][aã]o|exclamation mark)\b", "!"),
    (r"\b(?:dois pontos|colon)\b", ":"),
    (r"\b(?:ponto e v[ií]rgula|semicolon)\b", ";"),
    (r"\b(?:v[ií]rgula|comma)\b", ","),
    (r"\b(?:abre par[eê]nteses|open parenthesis)\b", "("),
    (r"\b(?:fecha par[eê]nteses|close parenthesis)\b", ")"),
    (r"\b(?:abre aspas|open quote)\b", '"'),
    (r"\b(?:fecha aspas|close quote)\b", '"'),
)

_OUTPUT_ACTIONS = {"insert", "insert_enter", "clipboard", "history"}


def remove_fillers(text: str) -> str:
    result = text
    for pattern in _FILLER_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    return result


def apply_spoken_commands(text: str) -> str:
    result = text
    for pattern, replacement in _SPOKEN_COMMANDS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = re.sub(r" *\n *", "\n", result)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    return result


def normalize_formatting(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=[^\s\n\"')\]}])", r"\1 ", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)

    chars = list(text.strip())
    capitalize_next = True
    for index, char in enumerate(chars):
        if capitalize_next and char.isalpha():
            chars[index] = char.upper()
            capitalize_next = False
        elif char in ".!?\n":
            capitalize_next = True
        elif not char.isspace():
            capitalize_next = False
    return "".join(chars).strip()


def process_transcript(
    text: str,
    *,
    spoken_commands: bool = True,
    remove_filler_words: bool = True,
    smart_formatting: bool = True,
) -> str:
    result = text.strip()
    if spoken_commands:
        result = apply_spoken_commands(result)
    if remove_filler_words:
        result = remove_fillers(result)
    if smart_formatting:
        result = normalize_formatting(result)
    return result.strip()


def process_stream_delta(text: str, *, spoken_commands: bool = True) -> str:
    """Process a live suffix without rewriting text already inserted."""
    if not spoken_commands:
        return text
    return apply_spoken_commands(text)


def resolve_output_action(mode: dict, default_action: str) -> str:
    """Resolve an optional profile override against the global default."""
    fallback = default_action if default_action in _OUTPUT_ACTIONS else "insert"
    selected = str(mode.get("output_action") or "default")
    return selected if selected in _OUTPUT_ACTIONS else fallback


def output_action_allows_insertion(output_action: str) -> bool:
    return output_action in {"insert", "insert_enter"}


def should_process_final_transcript(
    *,
    streaming: bool,
    output_action: str,
    needs_recovery: bool,
) -> bool:
    """Return whether the final text still needs the complete post-processing pass."""
    return (
        not streaming
        or needs_recovery
        or not output_action_allows_insertion(output_action)
    )


def should_submit_enter(
    *,
    output_action: str,
    can_inject: bool,
    injected: bool,
    needs_recovery: bool,
) -> bool:
    """Gate Enter so a divergent streaming result can never be submitted."""
    return (
        output_action == "insert_enter"
        and can_inject
        and injected
        and not needs_recovery
    )


def mode_for_target(
    modes: Iterable[dict],
    active_mode_id: str,
    process_name: str | None,
    window_title: str | None,
) -> dict:
    available = [mode for mode in modes if isinstance(mode, dict)]
    haystack = f"{process_name or ''}\n{window_title or ''}".lower()
    for mode in available:
        patterns = mode.get("app_patterns") or []
        if any(str(pattern).lower() in haystack for pattern in patterns if str(pattern).strip()):
            return mode
    for mode in available:
        if mode.get("id") == active_mode_id:
            return mode
    return available[0] if available else {
        "id": "default",
        "name": "Natural",
        "output_action": "default",
        "remove_fillers": True,
        "spoken_commands": True,
    }
