"""Tests for decision codes and primary-decision selection."""

from app.api.primary import pick_primary_decision
from app.brain.codes import assign_decision_codes


def test_codes_follow_date_then_title():
    codes = assign_decision_codes(
        [
            ("c", "Beta", "2026-03-01"),
            ("a", "Zeta", "2026-01-01"),
            ("b", "alpha", "2026-03-01"),
            ("u", "No date", None),
        ]
    )
    assert codes == {"a": "DEC-01", "b": "DEC-02", "c": "DEC-03", "u": "DEC-04"}


def test_codes_are_deterministic_regardless_of_input_order():
    rows = [("x", "One", "2026-01-02"), ("y", "Two", "2026-01-01"), ("z", "Three", "2026-01-02")]
    assert assign_decision_codes(rows) == assign_decision_codes(list(reversed(rows)))


def test_codes_widen_past_99():
    rows = [(str(i), f"T{i:03d}", "2026-01-01") for i in range(120)]
    codes = assign_decision_codes(rows)
    assert codes["0"] == "DEC-001"
    assert codes["119"] == "DEC-120"


def test_primary_prefers_quoted_title_and_cited_source():
    answer = 'The decision to "Migrate session storage from Postgres to Redis cluster" (TICK-101) was superseded.'
    decisions = [
        ("d_other", "Deprecate legacy RabbitMQ clusters in favor of Redis"),
        ("d_redis", "Migrate session storage from Postgres to Redis cluster to eliminate contention"),
    ]
    assert (
        pick_primary_decision(answer, decisions, {"d_redis": 1, "d_other": 0}, set()) == "d_redis"
    )


def test_primary_demotes_superseded_when_otherwise_tied():
    decisions = [("old", "Old thing here now"), ("new", "New thing here now")]
    cited = {"old": 0, "new": 1}
    assert pick_primary_decision("both", decisions, cited, set()) == "old"
    assert pick_primary_decision("both", decisions, cited, {"old"}) == "new"


def test_primary_is_none_without_candidates():
    assert pick_primary_decision("nothing", [], {}, set()) is None
