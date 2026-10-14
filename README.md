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

## 5. Development & Deployment

### Prerequisites
- Python 3.12+ (managed via `uv` or `venv`)
- FalkorDB instance (Cloud or self-hosted)
- Groq API Key (or OpenAI / custom LLM endpoint)

### Local Development Setup
1. **Clone repository and configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials (FALKORDB_HOST, FALKORDB_PORT, FALKORDB_PASSWORD, GROQ_API_KEY, etc.)
   ```

2. **Install dependencies**:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e backend
   ```

3. **Run Linting & Unit Tests**:
   ```bash
   # Linting
   ruff check backend

   # Unit tests (mocked & isolated, no live external dependencies required)
   PYTHONPATH=backend pytest backend/tests/test_config.py backend/tests/test_compat.py backend/tests/test_models.py backend/tests/test_health.py -v

   # Integration test (against FalkorDB Cloud & Groq LLM)
   RUN_INTEGRATION_TESTS=1 PYTHONPATH=backend pytest backend/tests/test_integration.py -v -m integration
   ```

4. **Start the FastAPI Backend**:
   ```bash
   PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   Open `http://localhost:8000/health` to verify the service and FalkorDB ping.

### Docker Deployment
Run the production multi-stage backend container with persistent volume storage for LanceDB and SQLite:
```bash
docker compose up --build -d
```
Check health:
```bash
curl http://localhost:8000/health
```

### Keeping FalkorDB Cloud Free-Tier Active
FalkorDB Cloud free-tier instances may sleep if idle for extended periods. A lightweight keepalive query is provided:
```bash
python scripts/keepalive.py
```
To run periodically via crontab:
```bash
0 */6 * * * cd /path/to/decision-trace && /path/to/.venv/bin/python scripts/keepalive.py >> /var/log/falkordb_keepalive.log 2>&1
```

---

## 6. Credits & Attribution

- **FalkorDB**: Matrix-based Graph Database engine powered by GraphBLAS and OpenCypher ([FalkorDB](https://falkordb.com/) | [GitHub](https://github.com/FalkorDB/FalkorDB)).
- **Cognee**: Agentic Memory & Knowledge Graph Orchestration Engine ([Cognee](https://www.cognee.ai/) | [GitHub](https://github.com/topoteretes/cognee)). Distributed under the Apache-2.0 License.
- **cognee-community-hybrid-adapter-falkor**: FalkorDB graph store adapter for Cognee ([PyPI](https://pypi.org/project/cognee-community-hybrid-adapter-falkor/)).
- **FastEmbed**: Fast and light embedding runtime using `BAAI/bge-small-en-v1.5` ([FastEmbed](https://github.com/qdrant/fastembed)).
- **LanceDB**: Serverless vector database on disk ([LanceDB](https://github.com/lancedb/lancedb)).
