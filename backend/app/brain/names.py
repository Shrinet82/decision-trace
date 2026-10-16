"""Helpers for turning list-valued entity strings into individual names."""

import re

_SEPARATORS = re.compile(r"\s*(?:,|;|\band\b|&)\s*", re.IGNORECASE)
_SYSTEM_PREFIX = re.compile(r"^system:\s*", re.IGNORECASE)


def split_names(value: str | None) -> list[str]:
    """Split "A, B and C" into ["A", "B", "C"], dropping blanks and duplicates (order kept)."""
    if not value:
        return []
    cleaned = _SYSTEM_PREFIX.sub("", value.strip())
    seen: set[str] = set()
    names: list[str] = []
    for part in _SEPARATORS.split(cleaned):
        part = part.strip()
        if part and part.lower() not in seen:
            seen.add(part.lower())
            names.append(part)
    return names
