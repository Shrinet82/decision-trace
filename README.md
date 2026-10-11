# Decision-Trace (Company Brain)

A knowledge graph platform that answers:
> **"Why did we decide this, who decided it, what is it based on, and is it still valid?"**

Built for the **Graph Hacks: Context for AI Agents** Hackathon (Track 03: Company Brain) powered by **FalkorDB** and **Cognee**.

---

## 1. Overview

Organizations lose the context behind key decisions as teams change, tickets close, and meeting notes scatter. Traditional search retrieves keyword fragments, but cannot explain lineage, ownership, contradictions, or downstream impact.

**Decision-Trace** synthesizes three disparate organizational sources:
1. **SQL Database**: Relational entities (People, Teams, Projects, Systems, Ownership).
2. **Support Tickets**: Operational issues, discussions, and buried decisions.
3. **Meeting Notes**: Contextual discussions, rationale, alternatives considered, and policy changes.

Every question answered in Decision-Trace surfaces:
- Direct citations to underlying records.
- People and teams involved.
- The **exact FalkorDB graph path** traversed to validate the answer.
- **Decision Health** (Active, Superseded, Contradicted, or Stale) computed via graph relationships.

---

## 2. Architecture

```text
Browser -> Cloudflare Pages (React + Vite + TypeScript)
              │ (HTTPS)
        EC2 / Server: Caddy -> FastAPI + Cognee ────► FalkorDB Cloud (Graph)
                                   │
                                   ├──► Local LanceDB (Vector Embeddings)
                                   └──► LLM API (Extraction & Q&A)
```

- **Primary Graph Database**: **FalkorDB Cloud** using OpenCypher queries to traverse entities, dependencies, and health states.
- **Knowledge Orchestration**: **Cognee** with community FalkorDB adapter (`cognee-community-hybrid-adapter-falkor`).
- **Vector Storage**: Local LanceDB on disk (conserving FalkorDB Cloud free-tier memory for the graph).
- **Backend**: Python 3.11–3.13, FastAPI, Pydantic, Uvicorn.
- **Frontend**: React, Vite, TypeScript, interactive graph visualization (Force-directed graph / Cytoscape).

---

## 3. Project Structure

```text
company-brain/
├── README.md               # Project documentation and setup guide
├── docker-compose.yml      # Containerized deployment specification
├── .env.example            # Environment variables template
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml      # Python dependencies (uv / pip)
│   └── app/
│       ├── main.py         # FastAPI entrypoint
│       ├── config.py       # Pydantic settings & environment validation
│       ├── schemas.py      # Request/response DTOs
│       ├── api/            # API endpoints (/ask, /graph, /decisions, /ingest, /health)
│       ├── brain/          # Memory layer, graph models, and Cypher traversals
│       └── ingest/         # Source processors (SQL DB, tickets, meeting notes)
├── data/                   # Synthetic enterprise dataset (SQL, tickets, notes)
├── scripts/                # Utility scripts (seed.py, keepalive.py)
└── frontend/               # React + Vite TypeScript web client
```

---

## 4. Graph Data Model

### Nodes
- `Person` (name, role, team)
- `Team` (name, department)
- `Project` (name, status)
- `System` (name, type, vendor)
- `Ticket` (id, title, status, opened, closed)
- `Meeting` (title, date)
- `Document` (filename, snippet)
- `Decision` (title, summary, rationale, decided_on, status, confidence)

### Relationships
- `(Decision)-[:DECIDED_BY]->(Person)`
- `(Decision)-[:ABOUT]->(System|Project)`
- `(Decision)-[:BASED_ON]->(Ticket|Meeting|Document)`
- `(Decision)-[:SUPERSEDES]->(Decision)`
- `(Decision)-[:CONTRADICTS]->(Decision)`
- `(Decision)-[:AFFECTS]->(System|Project|Team)`
- `(Person)-[:OWNS]->(System|Project)`
- `(Person)-[:MEMBER_OF]->(Team)`
- `(Ticket)-[:RAISED_BY]->(Person)`
- `(Ticket)-[:MENTIONS]->(System)`
- `(Meeting)-[:ATTENDED_BY]->(Person)`

### Graph-Native Decision Health Rules
- **Superseded**: Incoming `[:SUPERSEDES]` relation from a newer decision.
- **Contradicted**: Linked via `[:CONTRADICTS]` relation with an active decision.
- **Possibly Stale**: Decider no longer owns the target system or linked ticket was reopened.
- **Active**: Valid, uncontradicted decision with current owners.

---

## 5. Hackathon Credits & Acknowledgements

- Built for **Graph Hacks: Context for AI Agents** (WeMakeDevs x FalkorDB).
- Powered by [FalkorDB](https://falkordb.com/) graph database engine.
- Memory orchestration inspired by and utilizing [Cognee](https://github.com/topoteretes/cognee).
