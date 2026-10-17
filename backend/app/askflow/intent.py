"""Question intent, decided by rules (no LLM call), so the first step is instant and explainable.

why        why a decision was made, what replaced something, who decided it (the default retrieval)
impact     what is affected if a system is dropped or changed
expertise  who knows about a system
status     which decisions conflict / are superseded / are stale, which systems have no owner
other      anything else (handled like "why": retrieval around the matched entities)
"""

import re
from dataclasses import dataclass
from typing import Literal, Optional

Intent = Literal["why", "impact", "expertise", "status", "other"]
StatusFocus = Literal["conflicts", "superseded", "stale", "ownership", "overview"]

_IMPACT = re.compile(
    r"\b(affected|affects?|impact(ed|s)?|depends? on|dependen(t|cies|cy)|break|blast radius|"
    r"if we (drop|remove|retire|change|replace|deprecate|decommission|migrate|kill|turn off|shut down)|"
    r"what happens if)\b",
    re.IGNORECASE,
)
_EXPERTISE = re.compile(
    r"\b(who (knows|understands|is (the )?expert|is familiar|has (worked|experience))|"
    r"experts?\b|expertise|who should i (ask|talk to)|knows (the )?most|most about|familiar with)",
    re.IGNORECASE,
)
_STATUS_FOCUS: list[tuple[StatusFocus, re.Pattern[str]]] = [
    ("ownership", re.compile(r"\b(no owner|without (an )?owner|unowned|orphan(ed|s)?|owner(s)? (left|departed))\b", re.I)),
    ("conflicts", re.compile(r"\b(conflict(s|ing)?|contradict(s|ion|ions|ory)?|disagree)\b", re.I)),
    ("superseded", re.compile(r"\b(superseded|replaced decisions|overridden|outdated)\b", re.I)),
    ("stale", re.compile(r"\b(stale|out of date|need(s)? review|no longer valid)\b", re.I)),
]
_STATUS_GENERIC = re.compile(r"\b(health|status of (all|the) decisions|which decisions)\b", re.I)
_WHY = re.compile(r"\b(why|reason|rationale|what replaced|who decided|how come|motivation)\b", re.I)


@dataclass(frozen=True)
class ParsedIntent:
    intent: Intent
    # Status questions only: which part of decision/system health the question is about
    focus: Optional[StatusFocus] = None


def classify_intent(question: str) -> ParsedIntent:
    """Pick the intent from the wording. Order matters: impact and expertise phrasings are the
    most specific, then status (health-wide questions), then why."""
    q = question.strip()
    if _IMPACT.search(q):
        return ParsedIntent("impact")
    if _EXPERTISE.search(q):
        return ParsedIntent("expertise")
    for focus, pattern in _STATUS_FOCUS:
        if pattern.search(q):
            return ParsedIntent("status", focus)
    if _STATUS_GENERIC.search(q):
        return ParsedIntent("status", "overview")
    if _WHY.search(q):
        return ParsedIntent("why")
    return ParsedIntent("other")
