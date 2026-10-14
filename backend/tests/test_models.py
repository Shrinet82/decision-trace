from cognee.shared.llm_graph_model import datapoint_model_to_basemodel

from app.brain.models import (
    CompanyBrainGraph,
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
    person = Person(name="Sarah Connor", role="Principal Architect", member_of=team)

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

    prior_decision = Decision(title="Use Legacy Redis")
    decision = Decision(
        title="Adopt FalkorDB Cloud",
        summary="Migrated company knowledge graph from Redis to FalkorDB.",
        rationale="FalkorDB provides native OpenCypher and matrix-based graph execution.",
        status="accepted",
        confidence=0.95,
        decided_by=person,
        about_system=system,
        about_project=project,
        based_on=ticket,
        based_on_meeting=meeting,
        based_on_document=doc,
        supersedes=[prior_decision],
    )

    assert decision.title == "Adopt FalkorDB Cloud"
    assert decision.decided_by.name == "Sarah Connor"
    assert decision.about_system.name == "FalkorDB"
    assert decision.about_project.name == "Knowledge Brain"
    assert decision.based_on.ticket_id == "INC-402"
    assert decision.based_on_meeting.title == "Architecture Sync on Graph DBs"
    assert len(decision.supersedes) == 1
    assert decision.supersedes[0].title == "Use Legacy Redis"
    assert decision.status == "accepted"


def test_models_identity_and_index_fields():
    """Verify that identity_fields and search index_fields are declared on domain models."""
    assert "title" in (Decision._get_identity_fields() or [])
    assert "title" in Decision.model_fields["metadata"].default["index_fields"]
    assert "name" in (Person._get_identity_fields() or [])
    assert "name" in (System._get_identity_fields() or [])
    assert "ticket_id" in (Ticket._get_identity_fields() or [])


def test_company_brain_graph_conversion():
    """Verify CompanyBrainGraph transforms into a clean LLM BaseModel without infrastructure fields."""
    llm_model = datapoint_model_to_basemodel(CompanyBrainGraph, strip_metadata=True)
    schema = llm_model.model_json_schema()
    assert "decisions" in schema["properties"]
    assert "people" in schema["properties"]
    assert "systems" in schema["properties"]
    assert "tickets" in schema["properties"]
    assert "meetings" in schema["properties"]
    # Infrastructure fields must be stripped
    assert "id" not in schema["properties"]
    assert "version" not in schema["properties"]
