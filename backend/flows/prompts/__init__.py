"""Prompt files: rules.md (shared) + {te,hi,en}/style.md and examples_{restaurant,hospital}.md."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent
LANGS = ("te", "hi", "en")


@lru_cache
def load(name: str, lang: str | None = None) -> str:
    path = PROMPT_DIR / (f"{lang}/{name}" if lang else name)
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""
