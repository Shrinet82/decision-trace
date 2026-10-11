"""Domain DataPoint models for Decision-Trace.

Defines the entity nodes and relationship edges for the Company Brain graph.
In Cognee, classes subclassing DataPoint represent graph nodes, while fields
referencing other DataPoint instances represent directed graph edges named after
the field.
"""

from datetime import datetime
from typing import Any, ClassVar, Optional, Union

from cognee.infrastructure.engine import DataPoint
from pydantic import BaseModel, Field


class Team(DataPoint):
    """Represents an organizational team or department."""

    name: str = Field(..., description="Team name, e.g. Core Infrastructure")
    department: Optional[str] = Field(default=None, description="Department name, e.g. Engineering")

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["name"]}


class System(DataPoint):
    """Represents an internal tool, cloud service, database, or external vendor."""

    name: str = Field(..., description="System or tool name, e.g. FalkorDB, Kafka, AWS")
    system_type: Optional[str] = Field(
        default=None, description="Type, e.g. database, message-broker, cloud-vendor"
    )
    vendor: Optional[str] = Field(default=None, description="Vendor or provider name")

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["name", "vendor"]}


class Project(DataPoint):
    """Represents a product, engineering initiative, or organizational project."""

    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(default=None, description="Project goals and description")
    status: Optional[str] = Field(
        default="active", description="Project status: active, completed, planned"
    )

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["name", "description"]}


class Person(DataPoint):
    """Represents an employee, stakeholder, or decision maker."""

    name: str = Field(..., description="Full person name")
    role: Optional[str] = Field(default=None, description="Job title or role, e.g. Lead Architect")
    email: Optional[str] = Field(default=None, description="Contact email")
    member_of: Optional[Team] = Field(default=None, description="Team the person belongs to")
    owns: list[Union[System, Project]] = Field(
        default_factory=list, description="Systems or projects owned by this person"
    )

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["name", "role"]}


class Ticket(DataPoint):
    """Represents a support ticket, bug report, or issue ticket."""

    ticket_id: str = Field(..., description="External ticket ID, e.g. TICKET-1042")
    title: str = Field(..., description="Ticket title / summary")
    status: str = Field(default="open", description="Status: open, in-progress, resolved, closed")
    opened_at: Optional[datetime] = Field(default=None, description="Ticket opening timestamp")
    closed_at: Optional[datetime] = Field(default=None, description="Ticket resolution timestamp")
    raised_by: Optional[Person] = Field(default=None, description="Person who opened the ticket")
    mentions: list[System] = Field(
        default_factory=list, description="Systems or services mentioned in the ticket"
    )

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["title", "ticket_id"]}


class Meeting(DataPoint):
    """Represents a meeting or architecture review sync."""

    title: str = Field(
        ..., description="Meeting title, e.g. Architecture Review - Graph DB Migration"
    )
    meeting_date: Optional[str] = Field(default=None, description="Meeting date or timestamp")
    attended_by: list[Person] = Field(
        default_factory=list, description="Participants who attended the meeting"
    )

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["title"]}


class Document(DataPoint):
    """Represents a source file, markdown document, or snippet."""

    source_file: str = Field(..., description="Source file path or identifier")
    snippet: str = Field(..., description="Relevant text excerpt")

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["snippet", "source_file"]}


class Decision(DataPoint):
    """Represents an architectural, business, or organizational decision."""

    title: str = Field(..., description="Concise decision title")
    summary: str = Field(..., description="High-level description of what was decided")
    rationale: str = Field(..., description="Why the decision was made, constraints, tradeoffs")
    decided_on: Optional[str] = Field(default=None, description="Date decision was reached")
    status: str = Field(
        default="active",
        description="Health status: active, superseded, contradicted, possibly_stale",
    )
    confidence: float = Field(default=1.0, description="Extraction confidence score (0.0 to 1.0)")

    decided_by: Optional[Person] = Field(default=None, description="Person who made the decision")
    about: list[Union[System, Project]] = Field(
        default_factory=list, description="Systems or projects this decision concerns"
    )
    based_on: list[Union[Ticket, Meeting, Document]] = Field(
        default_factory=list,
        description="Evidence, tickets, or meeting notes underpinning the decision",
    )
    supersedes: list["Decision"] = Field(
        default_factory=list, description="Prior decisions replaced by this decision"
    )
    contradicts: list["Decision"] = Field(
        default_factory=list, description="Decisions with conflicting directives"
    )
    affects: list[Union[System, Project, Team]] = Field(
        default_factory=list, description="Entities impacted by this decision"
    )

    metadata: ClassVar[dict[str, Any]] = {"index_fields": ["title", "summary", "rationale"]}


class DecisionGraphExtraction(BaseModel):
    """Container schema for structured LLM graph extraction."""

    decisions: list[Decision] = Field(default_factory=list)
    people: list[Person] = Field(default_factory=list)
    systems: list[System] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)
    tickets: list[Ticket] = Field(default_factory=list)
    meetings: list[Meeting] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)
