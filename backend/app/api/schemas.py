"""Typed Pydantic Schemas for Decision-Trace REST API."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

HealthStatus = Literal["active", "superseded", "contradicted", "possibly_stale"]


class DecisionSummary(BaseModel):
    """Concise decision summary for list views."""

    id: str = Field(..., description="Unique decision ID")
    title: str = Field(..., description="Decision title")
    status: str = Field(..., description="Lifecycle status (e.g. accepted, reverted)")
    health: HealthStatus = Field(..., description="Computed health status")
    health_reason: str = Field(..., description="Explanation of computed health status")
    system: Optional[str] = Field(default=None, description="System name this decision governs")
    decided_by: Optional[str] = Field(default=None, description="Person who made the decision")
    decided_on: Optional[str] = Field(default=None, description="Date decision was made")


class SourceRef(BaseModel):
    """Reference to evidence sources (Ticket or Meeting)."""

    type: Literal["ticket", "meeting", "document"] = Field(..., description="Source entity type")
    id: str = Field(..., description="Identifier (e.g. TICK-101 or meeting title)")
    title: Optional[str] = Field(default=None, description="Title or summary")
    date: Optional[str] = Field(default=None, description="Date of the source")


class DecisionDetail(BaseModel):
    """Detailed decision view including graph connections and health audit."""

    id: str = Field(..., description="Unique decision ID")
    title: str = Field(..., description="Decision title")
    summary: str = Field(default="", description="Summary of the decision")
    rationale: str = Field(default="", description="Trade-offs, constraints, and why it was made")
    status: str = Field(..., description="Lifecycle status")
    health: HealthStatus = Field(..., description="Computed health status")
    health_reason: str = Field(..., description="Reason for the health status")
    decided_on: Optional[str] = Field(default=None, description="Date decision was reached")
    decided_by: Optional[str] = Field(default=None, description="Primary decider")
    people: list[str] = Field(
        default_factory=list, description="Related people (decider, attendees, assignees)"
    )
    systems: list[str] = Field(
        default_factory=list, description="Related systems (about_system, mentions)"
    )
    sources: list[SourceRef] = Field(
        default_factory=list, description="Originating tickets or meetings"
    )
    supersedes: list[str] = Field(
        default_factory=list, description="Decisions superseded by this decision"
    )
    superseded_by: list[str] = Field(
        default_factory=list, description="Decisions that supersede this decision"
    )
    contradicts: list[str] = Field(
        default_factory=list, description="Decisions contradicted by or contradicting this decision"
    )


class Citation(BaseModel):
    """Evidence citation linking an answer to a graph node."""

    type: Literal["ticket", "meeting", "decision", "document"] = Field(
        ..., description="Node label type"
    )
    id: str = Field(..., description="Node ID or unique key (e.g. TICK-101)")
    title: str = Field(..., description="Node title or descriptor")


class GraphNode(BaseModel):
    """Graph node in a serialized graph representation."""

    id: str = Field(..., description="Unique node identifier")
    label: str = Field(..., description="Primary node label (e.g. Decision, Person, System)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Node property attributes")


class GraphEdge(BaseModel):
    """Graph relationship edge."""

    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    type: str = Field(..., description="Relationship type (e.g. decided_by, supersedes)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Edge property attributes")


class GraphPath(BaseModel):
    """Connected subgraph traversed to formulate an answer."""

    nodes: list[GraphNode] = Field(default_factory=list, description="Nodes in the retrieved path")
    edges: list[GraphEdge] = Field(default_factory=list, description="Edges connecting the nodes")
    omitted_count: int = Field(
        default=0, description="Number of evidence nodes omitted due to the ~15 node cap"
    )


class AskRequest(BaseModel):
    """Natural language question payload."""

    question: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Natural language question to query the Company Brain (max 500 characters)",
    )
    dataset_name: Optional[str] = Field(
        default=None, description="Optional target dataset override"
    )


class AskResponse(BaseModel):
    """Grounded question answer with citations and evidence subgraph."""

    answer: str = Field(..., description="Grounded natural language answer")
    citations: list[Citation] = Field(
        default_factory=list, description="Sources cited in the answer"
    )
    people: list[str] = Field(default_factory=list, description="People referenced in the subgraph")
    graph_path: GraphPath = Field(
        default_factory=GraphPath, description="Exact subgraph used to answer"
    )


class GraphResponse(BaseModel):
    """Graph query result with type filtering."""

    nodes: list[GraphNode] = Field(default_factory=list, description="Graph nodes")
    edges: list[GraphEdge] = Field(default_factory=list, description="Graph edges")
    total_nodes: int = Field(default=0, description="Count of returned nodes")
    total_edges: int = Field(default=0, description="Count of returned edges")


class ResetResponse(BaseModel):
    """Administrative reset response."""

    status: str = Field(..., description="Reset status, e.g. success")
    dataset: str = Field(..., description="Target dataset that was purged")
    message: str = Field(..., description="Confirmation details")
