# Decision-Trace (Company Brain) - Comprehensive Agent Handoff Document

> **Purpose**: This document provides full contextual continuity for any incoming AI agent or engineer taking over the Decision-Trace repository. It describes the project mission, architecture, active cloud deployments, graph database topology, security posture, frontend implementation, and complete operational procedures.

---

## 1. Project Overview & Mission

* **Project Name**: Decision-Trace (Company Brain)
* **Hackathon Track**: Graph Hacks: Context for AI Agents (Track 03: Company Brain)
* **Core Value Proposition**: Answers organizational decision provenance:
  > *"Why did we decide this, who decided it, what is it based on, and is it still valid?"*
* **Target Audience**: Team leads, software architects, compliance officers, and auditors.
* **Core Philosophy**: Professional B2B SaaS layout with zero fluff, high legibility, deterministic evidence tracing, and strict graph-grounded provenance.

---

## 2. System Architecture & Live Cloud Deployments

Decision-Trace is built on a split-cloud, decoupled edge architecture:

```
[ User Browser ]
       │
       ▼ (HTTPS)
[ Cloudflare Pages: decision-trace.pages.dev ]
       │
       ├─► Static SPA: React 18 + TypeScript + Vite + Tailwind CSS + Cytoscape.js
       │
       └─► Cloudflare Pages Functions: Reverse Proxy (`frontend/functions/api/[[path]].ts`)
              │ (Strict path normalization, directory traversal blocking, endpoint whitelist)
              ▼ (HTTPS)
[ Railway Cloud: decision-trace-api-production.up.railway.app ]
       │
       ├─► FastAPI (Python 3.12, Uvicorn, Pydantic)
       │    ├── In-memory Per-IP Rate Limiting (20/min, 200/day) & Global Daily LLM Quota (500/day)
       │    └── Strict graph-edge citation validation & contradiction surfacing
       │
       ├─► FalkorDB Cloud Free-Tier (Port 62360, Plaintext TCP, `ssl=None`)
       │    └── OpenCypher traversals, health derivation (superseded, contradicted, possibly stale)
       │
       ├─► Local LanceDB on Disk (`.lancedb/` / `/app/data_storage/.lancedb`)
       │    └── FastEmbed `BAAI/bge-small-en-v1.5` semantic decision embeddings
       │
       └─► LiteLLM / Groq API (`qwen/qwen3.8-27b`)
            └── Grounded Q&A generation with multi-key rotation and exponential backoff retry
```

### Live URLs & Service Registry
| Service | Environment | Provider | URL / Endpoint | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Web App** | Production | Cloudflare Pages | `https://decision-trace.pages.dev` | React SPA dashboard with graph explorer |
| **Edge API Proxy** | Production | Cloudflare Pages Functions | `https://decision-trace.pages.dev/api/*` | Hardened reverse proxy to Railway backend |
| **Backend REST API** | Production | Railway Cloud | `https://decision-trace-api-production.up.railway.app` | FastAPI application (`/health`, `/ask`, `/decisions`, `/graph`) |
| **Primary Graph DB** | Production | FalkorDB Cloud | Host: port 62360 (TCP) | FalkorDB instance housing graph topology |
| **Keepalive Cron** | Automation | GitHub Actions | Scheduled every 6 hours | Pings FalkorDB to prevent cloud free-tier idle sleeping |

---

## 3. Database State & Canonical Graph Management

### A. Active Graph Topology
* **Active Graph Name**: `c87aa0cf-1c09-5296-8518-a3e8b9a1e744`
* **Configuration Sources**:
  * Local `.env`: `FALKORDB_GRAPH_NAME="c87aa0cf-1c09-5296-8518-a3e8b9a1e744"` and `DATASET_NAME="c87aa0cf-1c09-5296-8518-a3e8b9a1e744"`
  * Railway Environment: Configured in service variables for `decision-trace-api`
  * Backend routing: `backend/app/brain/memory.py` (`resolve_active_graph_name`) explicitly prioritizes `settings.FALKORDB_GRAPH_NAME` over legacy SQLite lookup tables.
* **Exact Node & Edge Counts**:
  * **148 Nodes Total**: 17 Decisions, 8 People, 8 Systems, 10 Teams, 10 Projects, 12 Tickets, 12 Meetings, 71 Documents.
  * **371 Edges Total**: `decided_by`, `about_system`, `based_on`, `supersedes`, `contradicts`, `owns`, `member_of`, etc.

### B. Backup Snapshot
* **Committed Snapshot File**: `data/snapshot/company_brain_snapshot.json`
* **Rule**: This committed snapshot is the canonical ground-truth backup. Any graph restore must reproduce exactly 148 nodes, 371 edges, and 17 decisions.
* **49-Node Test Graph Note**: A legacy test graph (`company_brain`, 49 nodes) exists on FalkorDB Cloud. Per instructions, **it must NOT be deleted without explicit confirmation from the user**. Once confirmed, `GRAPH.DELETE company_brain` can be executed, or `GRAPH.COPY` can be used if renaming is desired.

### C. Decision Status Integrity
All 17 decisions have been audited against evidence quotes and `data/GROUND_TRUTH.md`:
* 7 previous mismatches were fixed so that status is derived from quote verbs (`decided`, `adopted`, `standardize`, `migrated` -> `accepted`).
* Decision statuses in the active graph:
  1. `TICK-105`: Adopt Kafka for all event messaging (`accepted`)
  2. `TICK-106`: Adopt RabbitMQ for all event messaging (`accepted`) - *Explicitly contradicts Kafka*
  3. `TICK-101`: Migrate session storage to Redis (`accepted`) - *Superseded by Keycloak embedded cache*
  4. `TICK-102`: Migrate session storage to embedded Keycloak cache (`accepted`) - *Supersedes TICK-101*
  5. `TICK-109`: Deploy Prometheus Operator (`accepted`)
  6. `2026-04-12 Meeting`: Migrate application metrics to Prometheus Operator (`accepted`)
  7. `TICK-107`: Adopt HashiCorp Vault (`accepted`)
  8. `2026-06-08 Meeting`: Rotate database passwords to Vault dynamic secrets (`accepted`)
  9. `TICK-104`: Migrate analytics reporting to ClickHouse (`accepted`)
  10. `TICK-103`: Adopt Snowflake for analytics ETL (`accepted`)
  11. `TICK-110`: Deprecate RabbitMQ in favor of Redis PubSub for notifications (`accepted`)
  12. `TICK-111`: Standardize on Keycloak OAuth2 / OIDC (`accepted`)
  13. `2026-10-10 Meeting`: Decommission Snowflake warehouse in favor of ClickHouse (`accepted`)
  14. `dec_5b196394600e`: Standardize application traces on Datadog APM (`accepted`)
  15. Plus 3 foundational architectural decisions (`accepted`).

---

## 4. Citation Integrity & Contradiction Resolution

### A. Graph-Edge Grounding
* Located in `backend/app/api/ask.py`.
* Citations are verified strictly against real graph edges:
  ```python
  valid_based_on_targets = {e.target for e in edges_list if e.type == "based_on"}
  verified_citations = [c for c in citations_map.values() if c.id in valid_based_on_targets]
  ```
* Phantom citations (e.g., hallucinated `NOTE-2026-03-02` or `TICK-105` incorrectly cited for Vault) are mathematically eliminated.
* Contradiction citations (e.g., both TICK-105 and TICK-106) are retained when the response explains conflicting decisions.

### B. Contradiction Surfacing Rule
The system prompt in `backend/app/api/ask.py` instructs:
> *"If asked why a technology or system was chosen over another (e.g. Kafka vs RabbitMQ) and the context contains contradicting decisions, you MUST explicitly surface the contradiction, describe both decisions with their deciders and statuses, cite the respective tickets (e.g. TICK-105, TICK-106), and explain that the records show conflicting accepted decisions rather than a one-sided choice."*

---

## 5. Live 7 Benchmark Questions Performance

All 7 benchmark queries run through `POST https://decision-trace.pages.dev/api/ask` and are mirrored in `frontend/src/mocks/ask-*.json`:

| # | Question | Key Answer Element | Citations | Nodes / Edges | Status |
| :-: | :--- | :--- | :--- | :---: | :---: |
| **Q1** | *"Why did we choose Kafka over RabbitMQ?"* | Surfaces conflict: Alice Vance adopted Kafka (`TICK-105`) while Bob Martin adopted RabbitMQ (`TICK-106`, `Core Messaging Sync`). Both accepted; no one-sided choice. | `TICK-106`, `Core Messaging Sync`, `TICK-105`, `TICK-110` | 15 / 17 | Verified |
| **Q2** | *"Who owns Elasticsearch?"* | States Marcus Aurelius owns Elasticsearch and explicitly notes his departure on 2025-11-30. | `Observability Alignment`, `TICK-104`, `TICK-107`, `TICK-103` | 15 / 15 | Verified |
| **Q3** | *"What replaced Redis and why?"* | Explains Redis was not replaced overall, but session storage (`TICK-101`) was superseded by embedded Keycloak cache; Redis PubSub adopted for notifications (`TICK-110`). | `TICK-110`, `TICK-101` | 15 / 15 | Verified |
| **Q4** | *"Who decided Prometheus?"* | Explains Laura Croft decided Prometheus Operator (`TICK-109`) and Kevin Flynn migrated metrics (`Observability Alignment` meeting). | `Observability Alignment`, `TICK-109` | 15 / 14 | Verified |
| **Q5** | *"Where are secrets stored?"* | Explains HashiCorp Vault dynamic secrets decided by Diana Prince (`TICK-107`, `Security Architecture Review`). | `TICK-107`, `Security Architecture Review` | 14 / 15 | Verified |
| **Q6** | *"Quantum encryption migration plan"* | Unanswerable: accurately returns *"The answer is not found in the Company Brain."* | `0 citations` | 14 / 15 | Verified |
| **Q7** | *"Oracle database licensing"* | Unanswerable: accurately returns *"The answer is not found in the Company Brain."* | `0 citations` | 15 / 16 | Verified |

---

## 6. Security Hardening & Operational Safety

1. **Strict Credential Secrecy**:
   * **Rule**: Never print, echo, cat, or output `.env`, API keys, or raw tokens in logs or assistant responses.
   * Credentials belong strictly to environment variables and GitHub Secrets (`RAILWAY_TOKEN`).
2. **Cloudflare Reverse Proxy Guardrails** (`frontend/functions/api/[[path]].ts`):
   * URL decodes paths and blocks directory traversal (`..`, `\`, `//`). Tested: `/decisions/../admin` returns HTTP 404.
   * Strict endpoint whitelist: `GET /health`, `GET /decisions`, `GET /decisions/:id`, `GET /graph`, `POST /ask`. All other routes return HTTP 404.
3. **Backend Rate Limiting** (`backend/app/api/rate_limiter.py`):
   * Per-IP in-memory sliding window: 20 requests/minute, 200 requests/day.
   * Global LLM daily cost ceiling: 500 calls/day. Returns HTTP 429 when exceeded.
   * Input payload validation: Questions capped at 500 characters.
4. **FalkorDB Cloud Free-Tier Posture**:
   * Port 62360, plaintext TCP (`ssl=None`).
   * **Security boundary**: FalkorDB free tier provides no TLS; it is strictly dedicated to non-sensitive synthetic demo data.
   * Keepalive automation runs every 6 hours via `.github/workflows/falkordb-keepalive.yml`.

---

## 7. Frontend State & Visual Verification

* **Framework**: React 18, Vite 6, TypeScript 5.7, Tailwind CSS 3.4.
* **Layout**: Professional 240px responsive sidebar, clear hierarchy, high legibility.
* **Typography**: `@fontsource/overpass` (headings/body) and `@fontsource/overpass-mono` (tickets/code).
* **Graph Rendering**: Cytoscape.js with `cytoscape-dagre` layout.
  * Node states: `active`, `superseded`, `contradicted`, and `possibly_stale` (renders distinct dashed ring border).
  * Graph legend includes explicit "Possibly stale (dashed ring)" indicator.
* **Accessibility & E2E Testing**:
  * Automated Axe testing verifies **0 critical or serious WCAG 2.1 AA violations** in both light and dark modes.
  * All 12 responsive full-page screenshots captured and committed in `frontend/screenshots/`:
    * `ask-answer-1440-light.png` / `dark`
    * `ask-answer-1024-light.png` / `dark`
    * `ask-answer-390-light.png` / `dark`
    * `ask-not-found-1440-light.png` / `dark`
    * `ask-not-found-1024-light.png` / `dark`
    * `ask-not-found-390-light.png` / `dark`

---

## 8. Directory & File Reference Map

```text
.
├── AGENT_HANDOFF.md                  # This file: complete agent onboarding and handoff guide
├── README.md                         # Product documentation, Cypher schema, and overview
├── Dockerfile                        # Multi-stage root Dockerfile for Railway cloud deployments
├── railway.json                      # Railway cloud deployment configuration
├── docker-compose.yml                # Local containerization setup
├── .github/
│   └── workflows/
│       ├── deploy-backend.yml        # CI/CD: Automated Railway remote build & deploy on main push
│       └── falkordb-keepalive.yml    # Cron: 6-hour FalkorDB keepalive ping
├── backend/
│   ├── Dockerfile                    # Backend-scoped Dockerfile
│   ├── railway.json                  # Backend-scoped railway config
│   ├── pyproject.toml                # Dependencies (FastAPI, Cognee, FalkorDB, LiteLLM, LanceDB)
│   ├── app/
│   │   ├── main.py                   # FastAPI entrypoint, middleware, CORS, lifespan
│   │   ├── config.py                 # Pydantic Settings & environment validation
│   │   ├── api/
│   │   │   ├── ask.py                # POST /ask endpoint (graph retrieval, LLM Q&A, citations)
│   │   │   ├── decisions.py          # GET /decisions and GET /decisions/{id}
│   │   │   ├── graph.py              # GET /graph full topology extraction
│   │   │   ├── health.py             # GET /health healthcheck with FalkorDB ping
│   │   │   └── rate_limiter.py       # Per-IP rate limiting and daily LLM quota enforcement
│   │   ├── brain/
│   │   │   ├── memory.py             # FalkorDB connection, Cognee config, graph queries, retry logic
│   │   │   └── models.py             # Graph Node & Relationship Pydantic definitions
│   │   └── ingest/
│   │       ├── decisions_extractor.py# Decision extraction & verb-based status derivation
│   │       ├── notes_source.py       # Meeting notes ingestion parser
│   │       ├── tickets_source.py     # Tickets ingestion parser
│   │       └── sql_source.py         # Relational entities ingestion parser
│   └── tests/                        # 28 passing unit tests (test_status_integrity.py, test_api.py, etc.)
├── data/
│   ├── GROUND_TRUTH.md               # Human-curated ground truth for decisions & contradictions
│   ├── snapshot/
│   │   └── company_brain_snapshot.json # Canonical 148-node / 371-edge / 17-decision graph backup
│   ├── notes/                        # 12 Markdown meeting notes (IAM, messaging, secrets, etc.)
│   ├── tickets/                      # 12 Markdown ticket records (TICK-101 through TICK-112)
│   └── sql/                          # Schema and seed data for relational database
├── frontend/
│   ├── functions/api/[[path]].ts     # Cloudflare Pages Functions edge reverse proxy
│   ├── src/
│   │   ├── api/                      # API client, types, and benchmark mocks
│   │   ├── components/               # CytoscapeGraph, AppShell, StatusMarker, SourceDrawer, PathAsList
│   │   ├── pages/                    # AskPage, DecisionsPage, GraphPage
│   │   └── mocks/                    # Saved JSON responses from the live 7 benchmark questions
│   ├── e2e/                          # Playwright test suite (axe a11y, journey, screenshots)
│   └── screenshots/                  # 12 committed responsive screenshots (1440, 1024, 390 in light/dark)
└── scripts/
    ├── keepalive.py                  # Standalone keepalive script pinging FalkorDB
    └── seed.py                       # Pipeline script to ingest data into FalkorDB
```

---

## 9. Developer Runbook & Operations

### A. Running Backend Locally
```bash
# Activate virtual environment
source .venv/bin/activate

# Run FastAPI backend locally on port 8000
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run unit tests (excludes live cloud integration tests)
PYTHONPATH=backend pytest -m "not integration" backend/tests
```

### B. Running Frontend Locally
```bash
cd frontend

# Install dependencies if needed
npm install

# Start local Vite development server (port 5173)
npm run dev

# Run Playwright E2E tests & update screenshots
npm run build
npx playwright test
```

### C. Deploying to Cloud
1. **Backend (Railway)**:
   * Pushing to `main` with changes in `backend/**`, `Dockerfile`, or `.github/workflows/deploy-backend.yml` automatically triggers GitHub Actions workflow `.github/workflows/deploy-backend.yml`.
   * The action sets Railway variables `FALKORDB_GRAPH_NAME` and `DATASET_NAME` to `c87aa0cf-1c09-5296-8518-a3e8b9a1e744` and executes `railway up -c`.
2. **Frontend (Cloudflare Pages)**:
   * Build the frontend: `cd frontend && npm run build`
   * Deploy via Wrangler:
     ```bash
     cd frontend
     CLOUDFLARE_API_KEY="<YOUR_KEY>" CLOUDFLARE_EMAIL="<YOUR_EMAIL>" npx --yes wrangler pages deploy dist --project-name decision-trace --branch main
     ```

### D. Re-running the 7 Live Benchmark Questions
To query the production Cloudflare Pages proxy and refresh `frontend/src/mocks/ask-*.json`:
```bash
python3 scratch/run_7_questions_live.py
```

---

## 10. Open Decisions & Next Steps

1. **49-Node Test Graph Deletion**:
   * The 49-node test graph (`company_brain`) on FalkorDB Cloud is currently preserved.
   * If the user explicitly asks to remove it, run a Cypher command or script to execute `GRAPH.DELETE company_brain`.
   * If the user wants the 148-node graph to have the name `company_brain`, copy it first: `GRAPH.COPY c87aa0cf-1c09-5296-8518-a3e8b9a1e744 company_brain`, verify counts match (148 nodes, 371 edges), update settings, and only then delete the UUID graph.
2. **Additional Hackathon Features (Optional)**:
   * Dedicated `/decisions` list search/filter UI enhancements.
   * Full-screen interactive Cytoscape graph explorer enhancements.
