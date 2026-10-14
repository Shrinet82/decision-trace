"""Unit tests for decision reconciliation and identity resolution."""

from app.brain.reconciliation import (
    can_merge_decisions,
    compute_embedding_similarity,
    is_stub_node,
    normalize_title,
    pick_canonical_decision,
)


def test_normalize_title():
    """Verify normalization handles kebab-case slugs, punctuation, and extra whitespace."""
    raw = "migrate-session-storage-from-postgres-to-redis-cluster"
    expected = "migrate session storage from postgres to redis cluster"
    assert normalize_title(raw) == expected

    mixed = "  Adopt ClickHouse for Real-Time Analytics!  "
    assert "adopt clickhouse for real time analytics" in normalize_title(mixed)


def test_is_stub_node():
    """Verify stub detection accurately identifies reference placeholders."""
    stub_empty = {
        "id": 1,
        "title": "Migrate session storage to Redis",
        "summary": "",
        "rationale": "",
    }
    assert is_stub_node(stub_empty) is True

    stub_slug = {
        "id": 2,
        "title": "migrate-session-storage-from-postgres-to-redis-cluster",
        "summary": "Some short note",
        "rationale": "",
    }
    assert is_stub_node(stub_slug) is True

    full_decision = {
        "id": 3,
        "title": "Migrate session storage to Redis",
        "summary": "Switched sessions to Redis cluster to avoid connection pool exhaustion.",
        "rationale": "High latency on PostgreSQL.",
    }
    assert is_stub_node(full_decision) is False


def test_pick_canonical_decision():
    """Verify canonical selection prefers fully populated decisions over stubs."""
    stub = {
        "id": 10,
        "title": "migrate-session-storage-from-postgres-to-redis-cluster",
        "summary": "",
        "rationale": "",
    }
    canonical = {
        "id": 20,
        "title": "Migrate session storage to Redis",
        "summary": "Migrated session storage from Postgres to Redis.",
        "rationale": "Connection pool contention.",
    }

    chosen_can, chosen_dup = pick_canonical_decision(stub, canonical)
    assert chosen_can["id"] == 20
    assert chosen_dup["id"] == 10


def test_can_merge_decisions():
    """Verify tiebreak rules prevent accidental merges of conflicting systems or deciders."""
    d1 = {
        "id": 1,
        "title": "Migrate session storage to Redis",
        "system": "Redis",
        "person": "Dave Miller",
    }
    d2 = {
        "id": 2,
        "title": "migrate-session-storage-from-postgres-to-redis-cluster",
        "system": "Redis cluster",
        "person": "Dave Miller",
    }
    # Matching or substring system, same person
    assert can_merge_decisions(d1, d2, similarity=0.92, threshold=0.80) is True

    # Conflicting system tiebreak: Redis vs Kafka
    d_conflict_sys = {
        "id": 3,
        "title": "Migrate session storage to Kafka",
        "system": "Kafka",
        "person": "Dave Miller",
    }
    assert can_merge_decisions(d1, d_conflict_sys, similarity=0.88, threshold=0.80) is False

    # Conflicting decider tiebreak: Dave Miller vs Alice Chen
    d_conflict_person = {
        "id": 4,
        "title": "Migrate session storage to Redis",
        "system": "Redis",
        "person": "Alice Chen",
    }
    assert can_merge_decisions(d1, d_conflict_person, similarity=0.95, threshold=0.80) is False


def test_embedding_similarity():
    """Verify fastembed embedding cosine similarity accurately scores related titles."""
    sim_high = compute_embedding_similarity(
        "Migrate session storage to Redis cluster",
        "migrate-session-storage-from-postgres-to-redis-cluster",
    )
    assert sim_high > 0.85

    sim_low = compute_embedding_similarity(
        "Migrate session storage to Redis",
        "Adopt ClickHouse for real-time analytics event processing",
    )
    assert sim_low < 0.60
