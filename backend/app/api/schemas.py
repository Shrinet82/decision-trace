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
    decision_code: Optional[str] = Field(
        default=None, description="Stable human-readable code, e.g. DEC-07 (by decision date, then title)"
    )
    system: Optional[str] = Field(
        default=None, description="System name(s) this decision governs, comma-joined"
    )
    systems: list[str] = Field(default_factory=list, description="Each governed system")
    decided_by: Optional[str] = Field(
        default=None, description="Person(s) who made the decision, comma-joined"
    )
    deciders: list[str] = Field(default_factory=list, description="Each person who decided")
    decider_departed: bool = Field(
        default=False, description="True if any decider has left the company"
    )
    decided_on: Optional[str] = Field(default=None, description="Date decision was made")


class SourceRef(BaseModel):
    """Reference to evidence sources (Ticket or Meeting)."""

    type: Literal["ticket", "meeting", "document"] = Field(..., description="Source entity type")
    id: str = Field(..., description="Identifier (e.g. TICK-101 or meeting title)")
    title: Optional[str] = Field(default=None, description="Title or summary")
    date: Optional[str] = Field(default=None, description="Date of the source")


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


class PersonRef(BaseModel):
    """A person, with whether they have left the company."""

    name: str
    role: Optional[str] = None
    departed: bool = False
    leave_date: Optional[str] = None


class DecisionRef(BaseModel):
    """Compact decision reference used in lineage, timelines and entity pages."""

    id: str
    decision_code: Optional[str] = None
    title: str
    health: HealthStatus = "active"
    decided_on: Optional[str] = None
    deciders: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)


class LineageItem(DecisionRef):
    """A decision in a supersedes chain; depth 1 is the direct neighbour."""

    depth: int = 1


class Lineage(BaseModel):
    """Full supersedes chains (both directions) and contradiction links of a decision."""

    supersedes: list[LineageItem] = Field(
        default_factory=list, description="Older decisions this one replaces, transitively"
    )
    superseded_by: list[LineageItem] = Field(
        default_factory=list, description="Newer decisions that replace this one, transitively"
    )
    contradicts: list[DecisionRef] = Field(
        default_factory=list, description="Decisions this one contradicts (outgoing edge)"
    )
    contradicted_by: list[DecisionRef] = Field(
        default_factory=list, description="Decisions that contradict this one (incoming edge)"
    )


class SourceDetail(BaseModel):
    """An evidence source of a decision."""

    type: Literal["ticket", "meeting", "document"]
    id: str = Field(..., description="Ticket ID or meeting title")
    title: Optional[str] = None
    date: Optional[str] = None
    quote: Optional[str] = Field(
        default=None,
        description=(
            "Verbatim quote from this source, stored on the BASED_ON edge. Falls back to the "
            "decision-level quote only when it is found in this source's text or there is one source."
        ),
    )
    text: Optional[str] = Field(
        default=None, description="Verbatim body of the ticket or meeting note (first 1,500 chars)"
    )


class Impact(BaseModel):
    """Teams, projects and people within two hops of the decision's systems."""

    teams: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    people: list[PersonRef] = Field(default_factory=list)


class CypherQuery(BaseModel):
    name: str
    query: str
    params: dict[str, Any] = Field(default_factory=dict)
    ms: float


class CypherTraceOut(BaseModel):
    """The exact Cypher statements that produced a response, with timings."""

    queries: list[CypherQuery] = Field(default_factory=list)
    total_ms: float = 0.0


class SubgraphOut(BaseModel):
    """Deduplicated nodes and edges touched by a detail response. Node ids are 'Label:key'."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class DecisionDetail(BaseModel):
    """Detailed decision view including graph connections and health audit."""

    id: str = Field(..., description="Unique decision ID")
    decision_code: Optional[str] = Field(default=None, description="Stable code, e.g. DEC-07")
    decider_departed: bool = Field(
        default=False, description="True if any decider has left the company"
    )
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
    sources: list[SourceDetail] = Field(
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
    evidence_quote: Optional[str] = Field(default=None, description="Verbatim evidence quote")
    deciders: list[PersonRef] = Field(default_factory=list, description="Each decider")
    system_names: list[str] = Field(default_factory=list, description="Systems it is about")
    lineage: Lineage = Field(default_factory=Lineage)
    timeline: list[DecisionRef] = Field(
        default_factory=list,
        description="Every decision on the same system(s), oldest first, including this one",
    )
    impact: Impact = Field(default_factory=Impact)
    subgraph: SubgraphOut = Field(default_factory=SubgraphOut)
    cypher: CypherTraceOut = Field(default_factory=CypherTraceOut)


class Citation(BaseModel):
    """Evidence citation linking an answer to a graph node."""

    type: Literal["ticket", "meeting", "decision", "document"] = Field(
        ..., description="Node label type"
    )
    id: str = Field(..., description="Node ID or unique key (e.g. TICK-101)")
    title: str = Field(..., description="Node title or descriptor")


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
    primary_decision_id: Optional[str] = Field(
        default=None,
        description="ID of the decision the answer is mainly about (null when nothing was found)",
    )
    graph_path: GraphPath = Field(
        default_factory=GraphPath, description="Exact subgraph used to answer"
    )
    intent: Literal["why", "impact", "expertise", "status", "other"] = Field(
        default="other", description="How the question was understood"
    )
    entities: list["MatchedEntity"] = Field(
        default_factory=list, description="People, systems and decisions the question matched"
    )
    sections: list["AnswerSection"] = Field(
        default_factory=list, description="Grouped results (impact and status questions)"
    )
    experts: list["Expert"] = Field(
        default_factory=list, description="People ranked by evidence (expertise questions)"
    )
    trace: Optional["AskTrace"] = Field(
        default=None, description="Every step with its time and every Cypher query with its row count"
    )


class MatchedEntity(BaseModel):
    label: Literal["Person", "System", "Decision"]
    name: str
    id: Optional[str] = None
    decision_code: Optional[str] = None


class SectionItem(BaseModel):
    kind: Literal["decision", "person", "system", "team", "project", "ticket", "meeting"]
    name: str
    id: Optional[str] = None
    code: Optional[str] = Field(default=None, description="DEC code (decisions)")
    health: Optional[HealthStatus] = None
    detail: Optional[str] = None
    role: Optional[str] = None
    departed: bool = False
    leave_date: Optional[str] = None
    status: Optional[str] = Field(default=None, description="Ticket status (open / closed)")
    date: Optional[str] = None


class AnswerSection(BaseModel):
    key: str
    title: str
    items: list[SectionItem] = Field(default_factory=list)
    total: int = Field(default=0, description="Items found; items may be a shortened list")


class ExpertEvidence(BaseModel):
    decided: int = 0
    owns: int = 0
    meetings: int = 0
    tickets: int = 0


class Expert(BaseModel):
    name: str
    role: Optional[str] = None
    departed: bool = False
    leave_date: Optional[str] = None
    score: int = Field(..., description="Weighted evidence: decided x3, owns x3, meetings x2, tickets x1")
    evidence: ExpertEvidence
    decisions: list[str] = Field(default_factory=list, description="DEC codes decided")
    meetings: list[str] = Field(default_factory=list)
    tickets: list[str] = Field(default_factory=list)


class AskStep(BaseModel):
    step: Literal["understanding", "matching", "traversal", "health", "composing"]
    label: str
    status: Literal["done", "skipped", "error"]
    ms: float = 0.0
    detail: Optional[str] = None


class AskQuery(BaseModel):
    step: str
    name: str
    query: str
    params: dict[str, Any] = Field(default_factory=dict)
    rows: int
    ms: float


class AskTrace(BaseModel):
    steps: list[AskStep] = Field(default_factory=list)
    queries: list[AskQuery] = Field(default_factory=list)
    total_ms: float = 0.0


AskResponse.model_rebuild()


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



class SystemSummary(BaseModel):
    """A system with its owner and whether it is orphaned (owner has left)."""

    name: str
    system_type: Optional[str] = None
    vendor: Optional[str] = None
    owner: Optional[PersonRef] = None
    orphaned: bool = Field(default=False, description="True if the owner has left the company")
    decision_count: int = 0
    ticket_count: int = 0
    teams: list[str] = Field(default_factory=list)


class PersonInvolvement(PersonRef):
    """A person connected to a system, and how."""

    roles: list[str] = Field(
        default_factory=list, description="owner, decider, and/or tickets (raised or assigned)"
    )
    ticket_count: int = 0


class SystemDetail(SystemSummary):
    decisions: list[DecisionRef] = Field(default_factory=list, description="Oldest first")
    people: list[PersonInvolvement] = Field(default_factory=list)
    cypher: CypherTraceOut = Field(default_factory=CypherTraceOut)


class PersonSummary(PersonRef):
    teams: list[str] = Field(default_factory=list)
    systems_owned: list[str] = Field(default_factory=list)
    decision_count: int = 0


class OwnedSystem(BaseModel):
    name: str
    orphaned: bool = False


class PersonDetail(PersonSummary):
    start_date: Optional[str] = None
    email: Optional[str] = None
    teams_led: list[str] = Field(default_factory=list)
    projects_led: list[str] = Field(default_factory=list)
    owned: list[OwnedSystem] = Field(default_factory=list)
    decisions: list[DecisionRef] = Field(default_factory=list, description="Oldest first")
    tickets_raised: int = 0
    tickets_assigned: int = 0
    meetings_attended: int = 0
    cypher: CypherTraceOut = Field(default_factory=CypherTraceOut)
