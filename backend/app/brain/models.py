"""Domain DataPoint models for Decision-Trace.

Defines the entity nodes and relationship edges for the Company Brain graph.
In Cognee, classes subclassing DataPoint represent graph nodes, while fields
referencing other DataPoint instances represent directed graph edges named after
the field.
"""

from datetime import datetime
from typing import Annotated, Optional

from cognee.infrastructure.engine import DataPoint, FromIdentity
from pydantic import Field


class Team(DataPoint):
    """Represents an organizational team or department."""

    name: str = Field(..., description="Team name, e.g. Core Infrastructure")
    department: Optional[str] = Field(default=None, description="Department name, e.g. Engineering")

    metadata: dict = {"identity_fields": ["name"], "index_fields": ["name"]}


class System(DataPoint):
    """Represents an internal tool, cloud service, database, or external vendor."""

    name: str = Field(..., description="System or tool name, e.g. FalkorDB, Kafka, AWS")
    system_type: Optional[str] = Field(
        default=None, description="Type, e.g. database, message-broker, cloud-vendor"
    )
    vendor: Optional[str] = Field(default=None, description="Vendor or provider name")

    metadata: dict = {"identity_fields": ["name"], "index_fields": ["name", "vendor"]}


class Project(DataPoint):
    """Represents a product, engineering initiative, or organizational project."""

    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(default=None, description="Project goals and description")
    status: Optional[str] = Field(
        default="active", description="Project status: active, completed, planned"
    )

    metadata: dict = {"identity_fields": ["name"], "index_fields": ["name", "description"]}


class Person(DataPoint):
    """Represents an employee, stakeholder, or decision maker."""

    name: str = Field(..., description="Full person name")
    role: Optional[str] = Field(default=None, description="Job title or role, e.g. Lead Architect")
    email: Optional[str] = Field(default=None, description="Contact email")
    member_of: Annotated[Optional[Team], FromIdentity()] = Field(
        default=None, description="Team name the person belongs to"
    )

    metadata: dict = {"identity_fields": ["name"], "index_fields": ["name", "role"]}


class Ticket(DataPoint):
    """Represents a support ticket, bug report, or issue ticket."""

    ticket_id: str = Field(..., description="External ticket ID, e.g. TICKET-1042")
    title: str = Field(default="", description="Ticket title / summary")
    status: str = Field(default="open", description="Status: open, in-progress, resolved, closed")
    opened_at: Optional[datetime] = Field(default=None, description="Ticket opening timestamp")
    closed_at: Optional[datetime] = Field(default=None, description="Ticket resolution timestamp")
    raised_by: Annotated[Optional[Person], FromIdentity()] = Field(
        default=None, description="Person name who opened the ticket"
    )
    mentions: Annotated[list[System], FromIdentity()] = Field(
        default_factory=list, description="System names mentioned in the ticket"
    )

    metadata: dict = {"identity_fields": ["ticket_id"], "index_fields": ["ticket_id", "title"]}


class Meeting(DataPoint):
    """Represents a meeting or architecture review sync."""

    title: str = Field(
        ..., description="Meeting title, e.g. Architecture Review - Graph DB Migration"
    )
    meeting_date: Optional[str] = Field(default=None, description="Meeting date or timestamp")
    attended_by: Annotated[list[Person], FromIdentity()] = Field(
        default_factory=list, description="Names of participants who attended the meeting"
    )

    metadata: dict = {"identity_fields": ["title"], "index_fields": ["title"]}


class Document(DataPoint):
    """Represents a source file, markdown document, or snippet."""

    source_file: str = Field(..., description="Source file path or identifier")
    snippet: str = Field(default="", description="Relevant text excerpt")

    metadata: dict = {"identity_fields": ["source_file"], "index_fields": ["source_file", "snippet"]}


class Decision(DataPoint):
    """Represents an architectural, business, or organizational decision."""

    title: str = Field(..., description="Concise decision title")
    summary: str = Field(default="", description="High-level description of what was decided")
    rationale: str = Field(default="", description="Why the decision was made, constraints, tradeoffs")
    decided_on: Optional[str] = Field(default=None, description="Date decision was reached")
    status: str = Field(
        default="active",
        description="Health status: active, superseded, contradicted, possibly_stale",
    )
    confidence: float = Field(default=1.0, description="Extraction confidence score (0.0 to 1.0)")

    decided_by: Annotated[Optional[Person], FromIdentity()] = Field(
        default=None, description="Name of the Person who made the decision"
    )
    about_system: Annotated[Optional[System], FromIdentity()] = Field(
        default=None, description="Name of the System this decision concerns"
    )
    about_project: Annotated[Optional[Project], FromIdentity()] = Field(
        default=None, description="Name of the Project this decision concerns"
    )
    based_on: Annotated[Optional[Ticket], FromIdentity()] = Field(
        default=None,
        description="Ticket ID underpinning the decision",
    )
    based_on_meeting: Annotated[Optional[Meeting], FromIdentity()] = Field(
        default=None,
        description="Title of meeting underpinning the decision",
    )
    based_on_document: Annotated[Optional[Document], FromIdentity()] = Field(
        default=None,
        description="Source file underpinning the decision",
    )
    supersedes: Annotated[list["Decision"], FromIdentity()] = Field(
        default_factory=list, description="Titles of prior decisions replaced or superseded by this decision"
    )
    contradicts: Annotated[list["Decision"], FromIdentity()] = Field(
        default_factory=list, description="Titles of decisions in conflict or contradiction with this decision"
    )

    metadata: dict = {"identity_fields": ["title"], "index_fields": ["title", "summary", "rationale"]}


class CompanyBrainGraph(DataPoint):
    """Root graph container model for structured knowledge graph extraction."""

    decisions: list[Decision] = Field(default_factory=list)
    people: list[Person] = Field(default_factory=list)
    systems: list[System] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)
    tickets: list[Ticket] = Field(default_factory=list)
    meetings: list[Meeting] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)


# Backward-compatible alias
DecisionGraphExtraction = CompanyBrainGraph

