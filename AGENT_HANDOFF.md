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
       ├─► Static SPA: React 18 + TypeScript + Vite + Tailwind CSS + Cytoscape.js (Linear-style, light only)
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
| **Backend REST API** | Production | Railway Cloud | `https://decision-trace-api-production.up.railway.app` | FastAPI application (`/health`, `/ask`, `/decisions`, `/decisions/{code}`, `/graph`, `/systems`, `/people`, `POST /ingest` (SSE), `POST /ingest/reset`, `/changes`) |
| **Primary Graph DB** | Production | FalkorDB Cloud | Host: port 62360 (TCP) | FalkorDB instance housing graph topology |
| **Keepalive Cron** | Automation | GitHub Actions | Scheduled every 6 hours | Pings FalkorDB to prevent cloud free-tier idle sleeping |

---

## 3. Database State & Canonical Graph Management

### A. Active Graph Topology
* **Active Graph Name**: `c87aa0cf-1c09-5296-8518-a3e8b9a1e744` (the only graph on the FalkorDB instance).
* **Configuration Sources**:
  * Local `.env`: `FALKORDB_GRAPH_NAME` and `DATASET_NAME` are both the UUID above.
  * Railway Environment: set by `.github/workflows/deploy-backend.yml`.
  * Backend routing: `backend/app/brain/memory.py` (`resolve_active_graph_name`) maps the default dataset names (`company_brain`, `DATASET_NAME`) to `FALKORDB_GRAPH_NAME`.
* **Exact Node & Edge Counts**: **146 nodes, 374 edges**.
  * Nodes: 17 Decision, 15 Person, 12 System, 4 Team, 6 Project, 80 Ticket, 12 Meeting. (There are no Document nodes.)
  * Edges: `assigned_to` 80, `raised_by` 80, `mentions` 80, `attended_by` 38, `based_on` 18, `about_system` 18, `decided_by` 19, `member_of` 15, `owns` 12, `leads` 10, `supersedes` 3, `contradicts` 1.
* `decided_by` and `about_system` are one edge per person/system. List-valued names such as "A, B and C" are split at extraction (`app/brain/names.py`), and `split_composite_nodes` (`app/brain/reconciliation.py`, CLI `scripts/split_composites.py`) repairs existing graphs. It is idempotent.

### A2. Live ingest and the change log
* `POST /ingest` streams Server-Sent Events: `step` (reading, extracting_decisions, extracting_people, matching, linking, writing, health), `graph` (mini-graph updates), then `diff` or `error`. Pipeline in `backend/app/ingest/live.py`; it reuses the two-pass extractor prompts, verifies every quote is verbatim in the text, matches names to existing Person/System nodes (no duplicates; phrases like "Kafka for all event messaging" map to Kafka; long non-name phrases never become systems), and asks an LLM judge per (new decision, existing decision on a mentioned system) for supersedes / contradicts / reaffirms / none.
* Every node and edge it creates has `{demo_ingest_id, ingested_at}`. A person leaving updates `is_active`/`leave_date` on the existing node and records the previous values; this propagates to `decider_departed`, possibly_stale and orphaned systems.
* `POST /ingest/reset` deletes only tagged items, restores recorded values, and leaves the graph byte-identical to its frozen state (verified by `tests/test_ingest_live.py` with a content hash).
* The activity log (`GET /changes`) is stored in a separate graph, `<graph>__changes`, so reset never leaves residue in the main graph.
* Guardrails: 3 ingest/reset requests per minute per IP, one at a time (409 when busy), text 1-5,000 chars, 45 s timeout per LLM call, rollback of tagged data if a run fails mid-write.

### A3. Performance
* Detail endpoints use at most 3 Cypher statements, run concurrently in worker threads (`query_graph_threaded`, `CypherTrace.gather`). The health map and decision codes are cached for 5 minutes and refreshed in the background every 4 minutes (`_keep_caches_warm` in `server.py`), so requests never pay for them. Responses carry `Server-Timing: app;dur=<ms>`.

### B. Backup Snapshot
* **Committed Snapshot File**: `data/snapshot/company_brain_snapshot.json` (146 nodes, 374 edges, 17 decisions; Person 15 and System 12 match `data/GROUND_TRUTH.md`).
* Re-freeze with `PYTHONPATH=backend python scripts/restore_snapshot.py export company_brain` (read-only).
* Ticket and Meeting nodes carry `body` (verbatim, first 1,500 chars) and every BASED_ON edge carries its own verbatim `quote`. For an existing graph, `scripts/backfill_source_text.py` adds them in place (idempotent, never deletes).
* **DANGER**: `scripts/seed.py` and `scripts/restore_snapshot.py restore` call `reset(delete_all_graphs=True)`, which deletes EVERY graph on the instance, including production. Never run them against the live instance without a fresh snapshot and an explicit decision to rebuild.
* The legacy 49-node test graph `company_brain` and all eval/test graphs have been deleted; the production graph is the only one left.

### C. Decision Health (live counts)
* **12 active, 3 superseded, 2 contradicted, 0 possibly stale.**
* Rules (`backend/app/brain/health.py`), in precedence order: superseded, contradicted, possibly stale, active.
  * **Possibly stale**: a person who DECIDED it has left (`is_active = false` or a past `leave_date`), or it is older than 180 days with no newer decision about its systems. Superseded and contradicted decisions are never stale.
  * Every decision also exposes `decider_departed` (true if any decider left), whatever its health. The UI's "decider still on team" check and "decider left the company" hint use it.
* **Why 0 stale:** no Elasticsearch decision exists in the corpus. The 2026-07-14 meeting note only says ownership "needs reassignment"; it names no decider and no decision verb, and the quote in `data/GROUND_TRUTH_ADDENDUM.md` ("Alice Vance decided: ...") does not appear in the file, so the verified extractor correctly does not emit it. Marcus Aurelius (left 2025-11-30) owns Elasticsearch but decided nothing. The orphaned-system fact is still visible: `evaluate.py` reports it and `/ask "Who owns Elasticsearch?"` states he departed.
* **Orphaned systems:** a system whose `owns` person has left (`evaluate_system_orphans` in `health.py`). Today: Elasticsearch (Marcus Aurelius, left 2025-11-30). Exposed as `orphaned` on `/systems`.
* **Decision codes:** `/decisions`, `/ask` (graph_path Decision nodes) and `/graph` (Decision node properties) carry `decision_code` (`DEC-01`..`DEC-17`), numbered by decision date, then title (`backend/app/brain/codes.py`, computed on read). `/ask` also returns `primary_decision_id`, chosen server-side (`backend/app/api/primary.py`), or null if the answer found nothing.

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

## 5. Benchmark Questions (frozen in `frontend/src/mocks/ask-*.json`)

| # | Question | Result | Citations | Primary decision |
| :-: | :--- | :--- | :--- | :---: |
| Q1 | *Why did we choose Kafka over RabbitMQ?* | Surfaces the conflict: both decisions accepted, no one-sided choice. | `TICK-106`, `TICK-105` | DEC-07 |
| Q2 | *Who owns Elasticsearch?* | Marcus Aurelius, departed 2025-11-30. A pure ownership answer: no citations, no primary decision. | none | none |
| Q3 | *What replaced Redis for session storage?* | Embedded Keycloak cache replaced Redis for sessions. | `TICK-102`, `TICK-101` | DEC-11 |
| Q4 | *Who decided to adopt Prometheus?* | Kevin Flynn (metrics migration). | `Observability Platform Alignment`, `TICK-109` | DEC-08 |
| Q5 | *Why did we choose Vault for secret management?* | Vault dynamic secrets, decided by Diana Prince. | `TICK-107`, `Security Architecture Review` | DEC-05 |
| Q6 | *Quantum encryption migration plan* | "The answer is not found in the Company Brain." | none | none |
| Q7 | *Oracle database licensing* | "The answer is not found in the Company Brain." | none | none |

`/ask` returns only citations the answer text actually references and that come from real `based_on` edges, so an answer that cites nothing carries no sources.

---

## 6. Security Hardening & Operational Safety

1. **Strict Credential Secrecy**:
   * **Rule**: Never print, echo, cat, or output `.env`, API keys, or raw tokens in logs or assistant responses.
   * Credentials belong strictly to environment variables and GitHub Secrets (`RAILWAY_TOKEN`).
2. **Cloudflare Reverse Proxy Guardrails** (`frontend/functions/api/[[path]].ts`):
   * URL decodes paths and blocks directory traversal (`..`, `\`, `//`). Tested: `/decisions/../admin` returns HTTP 404.
   * Strict endpoint whitelist: `GET /health`, `GET /decisions`, `GET /decisions/:ref`, `GET /graph`, `GET /systems`, `GET /systems/:name`, `GET /people`, `GET /people/:name`, `POST /ask`. Names are limited to `[A-Za-z0-9 _.&'-]{1,80}` and re-encoded before forwarding. All other routes return HTTP 404.
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

* **Stack**: React 18, Vite 6, TypeScript 5.7, Tailwind CSS 3.4, TanStack Query, Cytoscape.js.
* **Design**: Linear-style, light only (Geist via Google Fonts, 13px base). Tokens are in `src/styles/tokens.css`. The mockups are in `frontend/design-ref/`.
* **Pages**: Ask (`/`), Decisions (`/decisions`, `/decisions/:code`), Systems (`/systems`, `/systems/:name`), People (`/people`, `/people/:name`), Explore (`/explore`, the full map; `/graph` redirects there), plus a command palette (Cmd/Ctrl+K) over decisions, systems and people. `/sources` is a placeholder.
* **Decision page** (`/decisions/DEC-11`): header (code, title, status + health reason, deciders with a "Left company" badge, date, systems), a Lineage graph (dagre left to right; top to bottom under 600px; sources -> decision, supersedes drawn old -> new dashed, contradicts dashed red, at most 25 nodes, click to navigate), system timeline, sources with quotes, impact, and a properties panel with "Show Cypher" (every query + ms).
* **Sidebar views**: Conflicts, Superseded, Orphaned systems (count from `/systems`).
* **Data**: `useDecisions`, `useGraph`, `useDecisionDetail`, `useAsk` in `src/api/hooks.ts`. Mock mode (localhost / port 4173) serves frozen fixtures from `src/mocks/`, loaded lazily.
* **Testing**: Vitest unit tests (54), Playwright journey plus axe on every page at 1440 and 390px (zero serious/critical violations), and `e2e/design-compare.spec.ts`, which renders the mockups next to the app.
* **Screenshots**: `frontend/screenshots/{ask,decisions,graph}-{1440,390}.png` and `compare-*.png` (design on the left, implementation on the right).

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
│   │   ├── main.py                   # Fast-binding ASGI entrypoint: /health answers at once, loads app.server in a thread
│   │   ├── server.py                 # The FastAPI app: middleware, CORS, lifespan, cache warmer
│   │   ├── config.py                 # Pydantic Settings & environment validation
│   │   ├── api/
│   │   │   ├── ask.py                # POST /ask endpoint (graph retrieval, one LLM call, citations, primary decision)
│   │   │   ├── systems.py            # GET /systems, /systems/{name} (owner, orphaned, timeline, people)
│   │   │   ├── people.py             # GET /people, /people/{name} (decisions, systems owned, teams)
│   │   │   ├── ingest.py             # POST /ingest (SSE), POST /ingest/reset, GET /changes
│   │   │   ├── primary.py            # Server-side choice of the answer's primary decision
│   │   │   ├── decisions.py          # GET /decisions and GET /decisions/{id}
│   │   │   ├── graph.py              # GET /graph full topology extraction
│   │   │   ├── health.py             # GET /health healthcheck with FalkorDB ping
│   │   │   └── rate_limiter.py       # Per-IP rate limiting and daily LLM quota enforcement
│   │   ├── brain/
│   │   │   ├── memory.py             # FalkorDB connection, Cognee config, graph queries, retry logic
│   │   │   ├── codes.py              # Stable DEC-NN decision codes
│   │   │   ├── names.py              # Splits list-valued names ("A, B and C")
│   │   │   ├── health.py             # Decision health rules (decider-based staleness)
│   │   │   ├── reconciliation.py     # Decision dedupe + split_composite_nodes
│   │   │   ├── lineage.py            # Decision page: chains, timeline, impact, subgraph (all Cypher)
│   │   │   ├── trace.py              # CypherTrace: records each query + ms for "Show Cypher"
│   │   │   ├── cache.py              # 5-minute cache for the health map and decision codes
│   │   │   └── models.py             # Graph Node & Relationship Pydantic definitions
│   │   └── ingest/
│   │       ├── decisions_extractor.py# Decision extraction & verb-based status derivation
│   │       ├── live.py               # Live ingest pipeline, diff, reset, change log
│   │       ├── source_text.py        # Source bodies, quote matching
│   │       ├── notes_source.py       # Meeting notes ingestion parser
│   │       ├── tickets_source.py     # Tickets ingestion parser
│   │       └── sql_source.py         # Relational entities ingestion parser
│   └── tests/                        # 39 unit tests + 6 integration tests (pytest -m integration)
├── data/
│   ├── GROUND_TRUTH.md               # Human-curated ground truth for decisions & contradictions
│   ├── GROUND_TRUTH_ADDENDUM.md      # Genuine unplanted decisions (note: its Elasticsearch quote is not in the source note)
│   ├── HOLDOUT_TRUTH.md, HOLDOUT2_TRUTH.md  # Ground truth for the two holdout sets
│   ├── holdout/, holdout2/           # Hand-written holdout tickets and meeting notes
│   ├── meeting_notes/, tickets.csv   # Main corpus (12 notes, 80 tickets)
│   ├── company.db                    # SQLite org data (people, teams, systems)
│   ├── verification_freeze_report.json # Baseline evaluation numbers from the original freeze
│   ├── snapshot/
│   │   └── company_brain_snapshot.json # Canonical 146-node / 374-edge / 17-decision graph backup
├── frontend/
│   ├── functions/api/[[path]].ts     # Cloudflare Pages Functions edge reverse proxy
│   ├── design-ref/                   # Static design mockups (visual source of truth)
│   ├── src/
│   │   ├── api/                      # Client, hooks, types (generated schema.d.ts), mock loader
│   │   ├── components/               # AppShell, PageFrame, CommandPalette, CytoscapeGraph, StatusIcon, ask/*
│   │   ├── pages/                    # Ask, Decisions, Decision, Systems, System, People, Person, Graph (Explore)
│   │   ├── utils/                    # model, answer, evidence, graphConverter, lineage, links, format
│   │   ├── mocks/                    # Frozen /ask, /decisions, /decisions/{id}, /graph responses
│   │   └── test/                     # Vitest unit tests
│   ├── e2e/                          # Playwright: app.spec.ts (journey, axe, screenshots), design-compare.spec.ts
│   └── screenshots/                  # ask/decisions/graph at 1440 and 390, plus compare-*.png
└── scripts/
    ├── evaluate.py                   # Scores the live graph against data/GROUND_TRUTH.md (read-only)
    ├── evaluate_holdout.py           # Cold extraction on data/holdout (own dataset)
    ├── evaluate_holdout2.py          # Cold extraction on data/holdout2 (own dataset)
    ├── split_composites.py           # Splits list-valued Person/System nodes (idempotent)
    ├── backfill_source_text.py       # Adds source bodies + per-source quotes in place (idempotent)
    ├── capture_fixtures.py           # Refreshes frontend/src/mocks from the current backend + graph
    ├── restore_snapshot.py           # export (safe) / restore (DELETES ALL GRAPHS)
    ├── seed.py                       # Full pipeline (DELETES ALL GRAPHS first)
    ├── generate_synthetic_dataset.py # Regenerates data/
    └── keepalive.py                  # Standalone keepalive script pinging FalkorDB
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

### D. Refreshing the frozen mocks
After changing the API shape or the data, regenerate the frontend fixtures (read-only against the graph; 7 LLM calls):
```bash
PYTHONPATH=backend python scripts/capture_fixtures.py
cd frontend && npm run generate-api   # only if backend schemas changed (needs a fresh frontend/openapi.json)
```

### E. Evaluations
```bash
PYTHONPATH=backend python scripts/evaluate.py                 # live graph vs data/GROUND_TRUTH.md (read-only)
BYPASS_EXTRACTION_CACHE=1 PYTHONPATH=backend python scripts/evaluate_holdout.py    # cold extraction, own dataset
BYPASS_EXTRACTION_CACHE=1 PYTHONPATH=backend python scripts/evaluate_holdout2.py
```
Scoring is per decision (rows are grouped by decision id/title). The holdout scripts reset only their own dataset, leave a graph behind, and should be deleted afterwards.

---

## 10. Open Items

1. **Orphaned Elasticsearch has no decision in the corpus** (see 3C). If a stale-by-departed-decider demo is wanted, add a source document in which a departed person decides something; do not edit extraction to invent one.
2. `scripts/seed.py` and `restore_snapshot.py restore` delete every graph. Consider guarding `reset(delete_all_graphs=True)` behind an explicit confirmation flag.
3. `/sources` is a placeholder page.
