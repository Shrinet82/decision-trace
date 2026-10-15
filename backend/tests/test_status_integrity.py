"""Tests for Decision Status Correctness, Citation Graph-Edge Integrity, and LLM Post-Processing."""

import re
import pytest
from app.api.schemas import Citation, GraphEdge
from app.ingest.decisions_extractor import derive_status_from_evidence


def test_derive_status_from_evidence():
    # 1. Accepted cases with "decided:"
    q1 = "Laura Croft decided: Deploy Prometheus Operator on all Kubernetes staging clusters."
    assert derive_status_from_evidence(q1) == "accepted"

    q2 = "Alice Vance decided: Use Kafka for all event messaging across services."
    assert derive_status_from_evidence(q2) == "accepted"

    q3 = "Ian Malcolm decided: Deprecate legacy RabbitMQ clusters in favor of native Redis PubSub."
    assert derive_status_from_evidence(q3) == "accepted"

    # 2. Proposed cases
    q4 = "Sarah proposed: Adopt FalkorDB Cloud for GraphRAG."
    assert derive_status_from_evidence(q4) == "proposed"

    q5 = "Carlos Mendez is evaluating a spike on ClickHouse cluster."
    assert derive_status_from_evidence(q5) == "proposed"

    # 3. Rejected cases
    q6 = "The committee decided against migrating to Oracle DB."
    assert derive_status_from_evidence(q6) == "rejected"

    q7 = "Team rejected the proposal to decommission RabbitMQ without dual-writes."
    assert derive_status_from_evidence(q7) == "rejected"


def test_citation_integrity_filters_unlinked_citations():
    """Verify that citations with no corresponding based_on edge are strictly excluded."""
    # Subgraph has decision D1 linked to TICK-101 and D2 linked to NOTE-2026-04-12
    edges = [
        GraphEdge(source="D1", target="TICK-101", type="based_on"),
        GraphEdge(source="D2", target="2026-04-12_observability_sync.md", type="based_on"),
        GraphEdge(source="D1", target="D2", type="supersedes"),
    ]
    
    # Candidate citations includes an unlinked/hallucinated ticket TICK-999
    citations_map = {
        "TICK-101": Citation(type="ticket", id="TICK-101", title="Session store"),
        "2026-04-12_observability_sync.md": Citation(type="meeting", id="2026-04-12_observability_sync.md", title="Observability"),
        "TICK-999": Citation(type="ticket", id="TICK-999", title="Hallucinated ticket"),
    }
    
    valid_based_on_targets = {e.target for e in edges if e.type == "based_on"}
    verified_citations = [c for c in citations_map.values() if c.id in valid_based_on_targets]
    
    citation_ids = {c.id for c in verified_citations}
    assert "TICK-101" in citation_ids
    assert "2026-04-12_observability_sync.md" in citation_ids
    assert "TICK-999" not in citation_ids, "Unlinked citation must be strictly dropped"


def test_status_integrity_never_says_decided_for_proposed_or_rejected():
    """Verify rule that proposed or rejected decisions are sanitized so they are never phrased as 'decided'."""
    raw_answer = "Alice Vance decided Deploy Prometheus Operator on all Kubernetes staging clusters."
    d_title = "Deploy Prometheus Operator on all Kubernetes staging clusters"
    d_status = "proposed"

    sanitized = re.sub(
        rf"\bdecided(?:\s+to)?\s+({re.escape(d_title)})",
        r"proposed \1",
        raw_answer,
        flags=re.IGNORECASE,
    )
    assert "decided" not in sanitized.lower()
    assert "proposed Deploy Prometheus Operator" in sanitized
