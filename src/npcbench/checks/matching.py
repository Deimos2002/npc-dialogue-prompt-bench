"""Frozen phrase matching shared by the deterministic checks (protocol).

- A phrase matches case-insensitively; its words match across any run of whitespace; a
  match may not touch a word character on either side.
- The text is scanned left to right; at each position the longest matching phrase wins and
  scanning resumes after it, so overlapping phrases match once.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Straight and curly double quotes; single quotes double as apostrophes, so they never quote.
_QUOTED = re.compile(r'"[^"]*"|“[^”]*”')


def phrase_pattern(phrases: Iterable[str]) -> re.Pattern[str] | None:
    words = {tuple(word.casefold() for word in p.split()) for p in phrases if p.strip()}
    if not words:
        return None
    # Regex alternation takes the first alternative that matches, so longest goes first.
    ordered = sorted(words, key=lambda w: (-len(w), -len(" ".join(w)), w))
    alternatives = "|".join(r"\s+".join(re.escape(word) for word in w) for w in ordered)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def find_phrases(text: str, phrases: Iterable[str]) -> list[str]:
    """Every match in reading order, as the phrase's words casefolded and single-spaced."""
    pattern = phrase_pattern(phrases)
    if pattern is None:
        return []
    return [" ".join(match.casefold().split()) for match in pattern.findall(text)]


def straighten(text: str) -> str:
    """Curly apostrophes as straight ones, so "I’m" matches the phrase "i'm"."""
    return text.replace("’", "'")


def strip_quoted(text: str) -> str:
    """Blank out double-quoted spans, for rules where quoted text does not count."""
    return _QUOTED.sub(" ", text)
