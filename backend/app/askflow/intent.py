"""Question intent, decided by rules (no LLM call), so the first step is instant and explainable.

why        why a decision was made, what replaced something, who decided it (the default retrieval)
impact     what is affected if a system is dropped or changed
expertise  who knows about a system
status     which decisions conflict / are superseded / are stale, which systems have no owner
other      anything else (handled like "why": retrieval around the matched entities)
"""

import asyncio
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger("decision_trace.askflow.intent")

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
    # Set only when the model classified the question: the system or topic it is about
    entity: Optional[str] = None
    by_model: bool = False


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


# ---------------------------------------------------------------------------------------------
# Fallback: one cheap model call when no rule matches
# ---------------------------------------------------------------------------------------------

FALLBACK_TIMEOUT_SECONDS = 12.0
_CACHE_SIZE = 500
_cache: "OrderedDict[str, ParsedIntent]" = OrderedDict()

FALLBACK_PROMPT = (
    "Classify a question asked of a company knowledge base about engineering decisions, people and "
    "systems. Reply with JSON only: {\"intent\": ..., \"entity\": ...}.\n"
    "intent is one of:\n"
    "- impact: what is affected, lost, at risk or has to change if a system is dropped, replaced, changed or goes away\n"
    "- expertise: who to ask, who knows, who is the go-to person or can help with a system or technology\n"
    "- status: which decisions conflict, are outdated or stale, or which systems have no owner\n"
    "- why: why something was decided, who decided it, what it replaced\n"
    "- other: anything else\n"
    "entity is the system, technology or product the question is about, exactly as written in the "
    "question, or null."
)


def _cache_key(question: str) -> str:
    return " ".join(question.lower().split())


async def _ask_model(question: str) -> str:
    import litellm

    from app.api.rate_limiter import (
        budget_exceeded,
        estimate_tokens,
        record_llm_call,
        record_tokens,
    )
    from app.config import get_settings

    if budget_exceeded():
        raise RuntimeError("daily token budget used up")
    record_llm_call()
    response = await asyncio.wait_for(
        litellm.acompletion(
            model=get_settings().LLM_MODEL,
            messages=[{"role": "system", "content": FALLBACK_PROMPT}, {"role": "user", "content": question}],
            temperature=0.0,
            max_tokens=60,
        ),
        timeout=FALLBACK_TIMEOUT_SECONDS,
    )
    reply = response.choices[0].message.content or ""
    record_tokens(estimate_tokens(FALLBACK_PROMPT, question, reply), "intent")
    return reply


def parse_model_reply(reply: str) -> ParsedIntent:
    """Read the model's JSON; anything unexpected is 'other' (answered like a why question)."""
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        return ParsedIntent("other")
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return ParsedIntent("other")
    intent = str(data.get("intent", "")).strip().lower()
    if intent not in ("why", "impact", "expertise", "status"):
        return ParsedIntent("other", by_model=True)
    entity = data.get("entity")
    entity = entity.strip() if isinstance(entity, str) and entity.strip() else None
    # A status question has no focus from the model; show the whole picture
    return ParsedIntent(intent, "overview" if intent == "status" else None, entity, by_model=True)  # type: ignore[arg-type]


async def classify_with_fallback(question: str) -> ParsedIntent:
    """Rules first (instant, free). Only when none matches, ask the model once and remember the
    answer for that exact question. A failed or slow call leaves the question as 'other'."""
    parsed = classify_intent(question)
    if parsed.intent != "other":
        return parsed
    key = _cache_key(question)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    try:
        parsed = parse_model_reply(await _ask_model(question.strip()))
    except Exception as exc:  # noqa: BLE001 - classification must never break an answer
        logger.warning("Intent fallback failed: %s", exc)
        return parsed
    _cache[key] = parsed
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return parsed

