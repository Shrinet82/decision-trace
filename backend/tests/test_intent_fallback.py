"""Intent fallback: when no rule matches, one cached model call classifies the question."""

import json
from unittest.mock import AsyncMock

import pytest

from app.askflow import intent
from app.askflow.intent import classify_intent, classify_with_fallback, parse_model_reply

IMPACT = [
    ("What would we lose if Snowflake went away?", "Snowflake"),
    ("Which teams rely on Kafka?", "Kafka"),
    ("Who needs to be told before we touch Redis?", "Redis"),
]
EXPERTISE = [
    ("Who's our go-to person for Kafka?", "Kafka"),
    ("Who can help me with Postgres?", "Postgres"),
    ("Is anybody here a Keycloak guru?", "Keycloak"),
]


@pytest.fixture(autouse=True)
def clean_cache():
    intent._cache.clear()


@pytest.mark.parametrize("question, entity", IMPACT + EXPERTISE)
def test_rules_do_not_match_these_paraphrases(question, entity):
    assert classify_intent(question).intent == "other"


@pytest.mark.parametrize("kind, cases", [("impact", IMPACT), ("expertise", EXPERTISE)])
async def test_paraphrases_are_classified_by_the_model(monkeypatch, kind, cases):
    for question, entity in cases:
        reply = json.dumps({"intent": kind, "entity": entity})
        monkeypatch.setattr(intent, "_ask_model", AsyncMock(return_value=reply))
        parsed = await classify_with_fallback(question)
        assert (parsed.intent, parsed.entity, parsed.by_model) == (kind, entity, True)


async def test_rule_matches_never_call_the_model(monkeypatch):
    model = AsyncMock(return_value="{}")
    monkeypatch.setattr(intent, "_ask_model", model)
    assert (await classify_with_fallback("What's affected if we drop Snowflake?")).intent == "impact"
    model.assert_not_awaited()


async def test_answers_are_cached_by_question(monkeypatch):
    model = AsyncMock(return_value='{"intent": "expertise", "entity": "Kafka"}')
    monkeypatch.setattr(intent, "_ask_model", model)
    first = await classify_with_fallback("Who's our go-to person for Kafka?")
    second = await classify_with_fallback("  who's our GO-TO person for kafka? ")
    assert first == second and model.await_count == 1


async def test_a_failing_model_leaves_the_question_as_other(monkeypatch):
    monkeypatch.setattr(intent, "_ask_model", AsyncMock(side_effect=TimeoutError()))
    assert (await classify_with_fallback("Tell me something interesting")).intent == "other"


@pytest.mark.parametrize("reply", ["", "no json here", '{"intent": "poetry"}', '{"intent": 5}'])
def test_unusable_replies_are_other(reply):
    assert parse_model_reply(reply).intent == "other"


def test_reply_wrapped_in_text_or_fences_is_read():
    parsed = parse_model_reply('```json\n{"intent": "impact", "entity": " Snowflake "}\n```')
    assert (parsed.intent, parsed.entity) == ("impact", "Snowflake")
