"""Unit tests for domain DataPoint models and schema definitions."""

from app.brain.models import (
    Decision,
    Document,
    Meeting,
    Person,
    Project,
    System,
    Team,
    Ticket,
)


def test_models_instantiation():
    """Verify that all domain entities instantiate with proper field types and defaults."""
    team = Team(name="Platform Engineering", department="Tech")
    system = System(name="FalkorDB", system_type="graph-database", vendor="FalkorDB Inc")
    project = Project(name="Knowledge Brain", status="active")
    person = Person(
        name="Sarah Connor", role="Principal Architect", member_of=team, owns=[system, project]
    )

    ticket = Ticket(
        ticket_id="INC-402",
        title="High query latency on legacy Redis",
        raised_by=person,
        mentions=[system],
    )
    meeting = Meeting(title="Architecture Sync on Graph DBs", attended_by=[person])
    doc = Document(
        source_file="architecture_review.md", snippet="Selected FalkorDB for native GraphRAG."
    )

    decision = Decision(
        title="Adopt FalkorDB Cloud",
        summary="Migrated company knowledge graph from Redis to FalkorDB.",
        rationale="FalkorDB provides native OpenCypher and matrix-based graph execution.",
        status="active",
        confidence=0.95,
        decided_by=person,
        about=[system, project],
        based_on=[ticket, meeting, doc],
    )

    assert decision.title == "Adopt FalkorDB Cloud"
    assert decision.decided_by.name == "Sarah Connor"
    assert len(decision.about) == 2
    assert len(decision.based_on) == 3
    assert decision.status == "active"


def test_models_index_fields():
    """Verify that search index fields are declared on domain models."""
    assert "title" in Decision.metadata["index_fields"]
    assert "summary" in Decision.metadata["index_fields"]
    assert "name" in Person.metadata["index_fields"]
    assert "name" in System.metadata["index_fields"]
    assert "name" in Project.metadata["index_fields"]
    assert "title" in Ticket.metadata["index_fields"]
