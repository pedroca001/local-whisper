"""Map UI language codes to Whisper-compatible language + initial_prompt bias.

Whisper uses ISO 639-1 (single 'pt' for Portuguese — no BR/PT split). To bias
the model toward Brazilian vs European Portuguese, we feed an `initial_prompt`
written in the desired variant. The prompt nudges punctuation, vocabulary
('você' vs 'tu'), and contractions ('tô' vs 'estou') in that direction.

Returns: (whisper_language_or_None, initial_prompt_or_None)
- 'auto' -> (None, None) — Whisper auto-detects the language
- 'pt-BR' -> ('pt', BR-flavored prompt)
- 'pt-PT' -> ('pt', PT-flavored prompt)
- 'en' / 'es' / etc -> (code, None)
"""
from __future__ import annotations

PT_BR_PROMPT = (
    "Olá, tudo bem? A gente precisa terminar essa apresentação. "
    "Você consegue revisar o texto e enviar pro time até amanhã de manhã? "
    "Tô achando que ficou ótimo, mas dá uma olhada nas duas últimas páginas."
)

PT_PT_PROMPT = (
    "Olá, está tudo bem? Precisamos de terminar a apresentação. "
    "Consegues rever o texto e enviá-lo à equipa até amanhã de manhã? "
    "Estou a achar que ficou óptimo, mas dá uma vista de olhos nas duas últimas páginas."
)


def resolve(lang_code: str) -> tuple[str | None, str | None]:
    code = (lang_code or "").strip()
    if not code or code.lower() in ("auto", "multilingual", "none"):
        return None, None
    if code == "pt-BR":
        return "pt", PT_BR_PROMPT
    if code == "pt-PT":
        return "pt", PT_PT_PROMPT
    if code == "pt":
        # Backward compat — assume Brazilian Portuguese for legacy configs
        return "pt", PT_BR_PROMPT
    return code, None
