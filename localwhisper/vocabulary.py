from __future__ import annotations

import re


def default_replacements(vocabulary: list[str] | None) -> list[dict[str, str]]:
    words = {w.strip().lower() for w in (vocabulary or []) if w and w.strip()}
    if "claude" not in words and "claude.md" not in words:
        return []
    return [
        {"from": "cloud", "to": "CLAUDE"},
        {"from": "cloude", "to": "CLAUDE"},
        {"from": "claud", "to": "CLAUDE"},
        {"from": "cloud.md", "to": "CLAUDE.md"},
    ]


def apply_replacements(text: str, replacements: list[dict] | None, vocabulary: list[str] | None = None) -> str:
    if not text:
        return ""
    rules = list(replacements or [])
    for rule in default_replacements(vocabulary):
        if rule not in rules:
            rules.append(rule)

    out = text
    for rule in rules:
        src = str(rule.get("from", "")).strip()
        dst = str(rule.get("to", "")).strip()
        if not src or not dst:
            continue
        pattern = re.compile(rf"(?<![\w.]){re.escape(src)}(?![\w.])", re.IGNORECASE)
        out = pattern.sub(dst, out)
    return out
