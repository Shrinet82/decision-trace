"""Verbatim source text stored on Ticket and Meeting nodes, and per-source quotes."""

import re
from typing import Optional

BODY_LIMIT = 1500


def excerpt(text: Optional[str], limit: int = BODY_LIMIT) -> str:
    """The first `limit` characters of the text, verbatim (whitespace at the ends trimmed)."""
    return (text or "").strip()[:limit]


def ticket_body(row: dict[str, str]) -> str:
    """A ticket's body is its comments column."""
    return excerpt(row.get("comments"))


def meeting_body(file_content: str) -> str:
    """A meeting's body is the note file itself (header and notes)."""
    return excerpt(file_content)


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def quote_in(quote: Optional[str], body: Optional[str]) -> bool:
    """True if the quote appears verbatim (case and whitespace insensitive) in the body."""
    if not quote or not body:
        return False
    return normalize(quote) in normalize(body)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def sentence_stating(title: Optional[str], body: Optional[str]) -> Optional[str]:
    """The first sentence of `body` (verbatim) that states the decision titled `title`.

    Matches the title without its leading verb ("Adopt X for Y" -> "X for Y"), since sources
    phrase the same choice as "decided: Use X for Y". Returns None if no sentence matches.
    """
    if not title or not body:
        return None
    words = title.split()
    core = normalize(" ".join(words[1:]) if len(words) > 3 else title)
    for sentence in _SENTENCE_END.split(body.strip()):
        if core and core in normalize(sentence):
            return sentence.strip()
    return None
