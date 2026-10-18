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
| **Backend REST API** | Production | Railway Cloud | `https://decision-trace-api-production.up.railway.app` | FastAPI application (`/health`, `POST /ask`, `POST /ask/stream` (SSE), `/decisions`, `/decisions/{code}`, `/graph`, `/systems`, `/people`, `/sources`, `/sources/{kind}/{key}`, `POST /ingest` (SSE), `POST /ingest/reset`, `GET /ingest/status`, `/changes`) |
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

### A4. Ask pipeline (`backend/app/askflow/`)
* `POST /ask/stream` streams Server-Sent Events, and `POST /ask` runs the same generator and returns its final `done` payload, so the two always agree. Steps, each with `ms`:
  1. `understanding`: the intent, by rules in `intent.py` (no LLM call). The intents are `why | impact | expertise | status | other`; status questions also get a focus (`conflicts | superseded | stale | ownership | overview`).
  2. `matching`: one roster query, then whole-word name matching for people and systems, plus embedding matches on decision titles. Title matches need a score of 0.35, or 0.7 when the question already names a system, because unrelated titles score about 0.6 and would bury the facts.
  3. `traversal`: the Cypher for the intent, in `queries.py`.
  4. `health`: the cached health map. The pure functions in `assemble.py` build the evidence graph, sections and experts here.
  5. `composing`: one LLM call that only phrases the computed context, streamed as `token` events.
* Events: `step` (running / done / skipped), `query` (name, Cypher, params, rows, ms), `path` (graph_path, provisional primary, sections and experts, sent before the answer), `token`, then `done` or `error`. `done` carries `intent`, `entities`, `sections`, `experts` and `trace {steps, queries, total_ms}`.
* What each intent computes:
  * **impact** (one system): the decisions on it plus their full supersedes chains in both directions, deciders, owner and ticket participants, teams and projects two hops away (through the owner), and its tickets (open first, then the most recent). The primary decision is the newest one on the system that is still in force.
  * **expertise**: people ranked by weighted evidence: decided ×3, owns ×3, meeting attendee ×2 (meetings that are sources of its decisions or mention it), ticket participant ×1. People who have left are kept, flagged, and ranked last. There is no primary decision.
  * **status**: the conflict, superseded and stale lists, or system ownership (owner left, or no owner on record).
* An unanswerable question skips traversal and the model. If the model answers "not found", the path, citations and primary are cleared.
* Live results (2026-10-17, captured in `frontend/src/mocks/ask-stream.json`):
  * Keycloak "why": DEC-11.
  * Conflicts: DEC-04 and DEC-07 (primary DEC-07).
  * Impact of Snowflake: DEC-03, DEC-13 (through the chain) and DEC-17.
  * Kafka expertise: Alice Vance first (weight 9).
  * No owner: Elasticsearch.

### A5. Sources and demo safety
* `GET /sources` lists 80 tickets, 12 meeting notes, any ingested documents, and the 37 company.db records (systems, people, teams and projects), each with the number of decisions it backs. `GET /sources/{kind}/{key}` returns the full text and each linked decision's verbatim quote: the edge quote first, then the decision quote, but only if it appears in the text. It also returns people and systems, or a record's fields and connections.
* **Auto-reset**: `auto_reset_loop` (started in `server.py`) checks every minute and runs `reset_demo` 10 minutes after the latest ingest. `GET /ingest/status` returns `resets_at` and `seconds_left`, and the Add source drawer shows "Demo data resets in N min".

### B. Backup Snapshot
* **Committed Snapshot File**: `data/snapshot/company_brain_snapshot.json` (146 nodes, 374 edges, 17 decisions; Person 15 and System 12 match `data/GROUND_TRUTH.md`).
* Re-freeze with `PYTHONPATH=backend python scripts/restore_snapshot.py export company_brain` (read-only).
* Ticket and Meeting nodes carry `body` (verbatim, first 1,500 chars) and every BASED_ON edge carries its own verbatim `quote`. For an existing graph, `scripts/backfill_source_text.py` adds them in place (idempotent, never deletes).
* **Guarded**: `scripts/seed.py` and `scripts/restore_snapshot.py restore` call `reset(delete_all_graphs=True)`, which deletes every graph on the instance. They run only through `scripts/destructive_guard.py`, which requires:
  * `--i-know-this-deletes-all-graphs`;
  * `--force-production` as well, when `FALKORDB_GRAPH_NAME` is the production UUID;
  * the graph name typed back at a prompt.

  `restore_snapshot.py` now needs an explicit `export|restore` action; before, it restored when called with no arguments. `memory.reset()` itself refuses to delete every graph or the production graph unless the guard has opted in (`DECISION_TRACE_ALLOW_DESTRUCTIVE_RESET=1`, set only in that process), so a bare `reset()` (which targets `DATASET_NAME`) and `POST /admin/reset` (now a 403) can no longer delete production.
* The legacy 49-node test graph `company_brain` and all eval/test graphs have been deleted; the production graph is the only one left.

### C. Decision Health (live counts)
* **12 active, 3 superseded, 2 contradicted, 0 possibly stale.**
* Rules (`backend/app/brain/health.py`), in precedence order: superseded, contradicted, possibly stale, active.
  * **Possibly stale**: a person who DECIDED it has left (`is_active = false` or a past `leave_date`), or it is older than 180 days with no newer decision about its systems. Superseded and contradicted decisions are never stale.
  * Every decision also exposes `decider_departed` (true if any decider left), whatever its health. The UI's "decider still on team" check and "decider left the company" hint use it.
* **Why 0 stale:** no Elasticsearch decision exists in the corpus. The 2026-07-14 meeting note only says ownership "needs reassignment"; it names no decider and no decision verb, and the quote in `data/GROUND_TRUTH_ADDENDUM.md` ("Alice Vance decided: ...") does not appear in the file, so the verified extractor correctly does not emit it. Marcus Aurelius (left 2025-11-30) owns Elasticsearch but decided nothing. The orphaned-system fact is still visible: `evaluate.py` reports it and `/ask "Who owns Elasticsearch?"` states he departed.
* **Orphaned systems:** a system whose `owns` person has left (`evaluate_system_orphans` in `health.py`). Today: Elasticsearch (Marcus Aurelius, left 2025-11-30). Exposed as `orphaned` on `/systems`.
* **Decision codes:** `/decisions`, `/ask` (graph_path Decision nodes) and `/graph` (Decision node properties) carry `decision_code` (`DEC-01`..`DEC-17`), numbered by decision date, then title (`backend/app/brain/codes.py`, computed on read). `/ask` also returns `primary_decision_id`, chosen server-side: `primary.py` scoring for why-questions and the Cypher result for impact and status. It is null for expertise and for answers that found nothing.

## 4. Citation Integrity & Contradiction Resolution

### A. Graph-Edge Grounding
* Located in `backend/app/askflow/assemble.py` (`verified_citations`).
* Citations are verified strictly against real graph edges:
  ```python
  valid_based_on_targets = {e.target for e in edges_list if e.type == "based_on"}
  verified_citations = [c for c in citations_map.values() if c.id in valid_based_on_targets]
  ```
* Phantom citations (e.g., hallucinated `NOTE-2026-03-02` or `TICK-105` incorrectly cited for Vault) are mathematically eliminated.
* Contradiction citations (e.g., both TICK-105 and TICK-106) are retained when the response explains conflicting decisions.

### B. Contradiction Surfacing Rule
The why-prompt in `backend/app/askflow/pipeline.py` instructs:
> *"If asked why a technology or system was chosen over another (e.g. Kafka vs RabbitMQ) and the context contains contradicting decisions, you MUST explicitly surface the contradiction, describe both decisions with their deciders and statuses, cite the respective tickets (e.g. TICK-105, TICK-106), and explain that the records show conflicting accepted decisions rather than a one-sided choice."*

---

## 5. Benchmark Questions (frozen in `frontend/src/mocks/ask-*.json`)

| # | Question | Result | Citations | Primary decision |
| :-: | :--- | :--- | :--- | :---: |
| Q1 | *Why did we choose Kafka over RabbitMQ?* | Surfaces the conflict: both decisions accepted, no one-sided choice. | `TICK-106`, `TICK-105` | DEC-07 |
| Q2 | *Who owns Elasticsearch?* | Marcus Aurelius, departed 2025-11-30. A pure ownership answer: no citations, no primary decision. | none | none |
| Q3 | *What replaced Redis for session storage?* | Embedded Keycloak cache replaced Redis for sessions. | `TICK-102`, `TICK-101` | DEC-11 |
| Q4 | *Who decided to adopt Prometheus?* | Kevin Flynn (metrics migration). | `Observability Platform Alignment` | DEC-08 |
| Q5 | *Why did we choose Vault for secret management?* | Vault as the exclusive secret store, decided by Diana Prince. | `TICK-107`, `Security Architecture Review` | DEC-05 |
| Q6 | *Quantum encryption migration plan* | "The answer is not found in the Company Brain." | none | none |
| Q7 | *Oracle database licensing* | "The answer is not found in the Company Brain." | none | none |

`/ask` returns only citations the answer text actually references and that come from real `based_on` edges, so an answer that cites nothing carries no sources. The model decides which sources it mentions, so citation lists can vary slightly between runs (for example Q3 sometimes cites only TICK-102); the primary decisions are stable.

Suggested questions on the Ask page (also recorded in `ask-stream.json`): *Why did we move sessions to Keycloak?* (DEC-11), *Do any decisions conflict?* (DEC-04 / DEC-07), *What's affected if we drop Snowflake?* (DEC-03, DEC-13, DEC-17), *Who knows the most about Kafka?* (Alice Vance), *Which systems have no owner?* (Elasticsearch).

---

## 6. Security Hardening & Operational Safety

1. **Strict Credential Secrecy**:
   * **Rule**: Never print, echo, cat, or output `.env`, API keys, or raw tokens in logs or assistant responses.
   * Credentials belong strictly to environment variables and GitHub Secrets (`RAILWAY_TOKEN`).
2. **Cloudflare Reverse Proxy Guardrails** (`frontend/functions/api/[[path]].ts`):
   * URL decodes paths and blocks directory traversal (`..`, `\`, `//`). Tested: `/decisions/../admin` returns HTTP 404.
   * Strict endpoint whitelist: `GET /health`, `GET /decisions`, `GET /decisions/:ref`, `GET /graph`, `GET /systems`, `GET /systems/:name`, `GET /people`, `GET /people/:name`, `GET /sources`, `GET /sources/:kind/:key`, `POST /ask`, `POST /ask/stream`, `POST /ingest`, `POST /ingest/reset`, `GET /ingest/status`, `GET /changes`. Names are limited to `[A-Za-z0-9 _.&'-]{1,80}` (source keys also allow `( ) , :`, up to 120) and re-encoded before forwarding. Server-sent events are streamed through unbuffered. All other routes return HTTP 404.
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
* **Pages**: Home (`/`: ask box + suggestions, brain stats, "Needs attention" from `GET /attention`, "Recent changes" from `/changes`; an old `/?q=` link redirects to `/ask?q=`), Ask (`/ask`), Connect an agent (`/agents`: MCP URL + copy button, Claude Code / Claude Desktop / Cursor snippets, tool list with example prompts), Decisions (`/decisions`, `/decisions/:code`), Systems (`/systems`, `/systems/:name`), People (`/people`, `/people/:name`), Explore (`/explore`, the full map; `/graph` redirects there), Sources (`/sources`, with a type filter, counts, the last ingest, and a drawer with the full text and highlighted quotes; `?open=kind/key` deep-links a source), plus a command palette (Cmd/Ctrl+K) over decisions, systems and people.
* **Ask page**:
  * The answer streams in.
  * "How I found this" shows every step with its ms, the matched entities as chips, each Cypher query (collapsible) with its row count, and the total time. It sits in the right panel on desktop and in a disclosure above the answer under 900px.
  * Impact and status answers render as grouped sections; expertise renders as a ranked list with evidence bars built from the counts.
  * The evidence path rows animate in once; reduced motion turns that off. A why-path waits until the streamed text can no longer be "not found".
* **Decision page** (`/decisions/DEC-11`): header (code, title, status + health reason, deciders with a "Left company" badge, date, systems), a Lineage graph (dagre left to right; top to bottom under 600px; sources -> decision, supersedes drawn old -> new dashed, contradicts dashed red, at most 25 nodes, click to navigate), system timeline, sources with quotes, impact, and a properties panel with "Show Cypher" (every query + ms).
* **Sidebar views**: Conflicts, Superseded, Orphaned systems (count from `/systems`).
* **Data**: `useDecisions`, `useGraph`, `useDecisionDetail`, `useAsk` in `src/api/hooks.ts`. Mock mode (localhost / port 4173) serves frozen fixtures from `src/mocks/`, loaded lazily.
* **Testing**:
  * 157 Vitest unit tests.
  * Playwright: `app.spec.ts` (journey, axe, screenshots), `ingest.spec.ts`, `home-agents.spec.ts` (Home, Agents, axe + screenshots), `ask-stream.spec.ts` (streamed Ask, impact, expertise, status, Sources, axe and screenshots at 1440 and 390px) and `design-compare.spec.ts`.
  * Playwright runs with `reducedMotion: 'reduce'` and only in CI: no builds on the developer's machine.
  * Mock mode replays recorded Ask streams, waiting each step's recorded time (scaled 0.35, capped at 900 ms; instant under Vitest).
* **Screenshots**: `frontend/screenshots/{ask,decisions,graph}-{1440,390}.png` and `compare-*.png` (design on the left, implementation on the right).

---

## 8. Directory & File Reference Map

```text
.
├── docs/AGENT_HANDOFF.md             # This file: complete agent onboarding and handoff guide
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
│   │   │   ├── ask.py                # POST /ask and POST /ask/stream (thin wrappers over app/askflow)
│   │   │   ├── sources.py            # GET /sources, /sources/{kind}/{key}
│   │   │   ├── systems.py            # GET /systems, /systems/{name} (owner, orphaned, timeline, people)
│   │   │   ├── people.py             # GET /people, /people/{name} (decisions, systems owned, teams)
│   │   │   ├── ingest.py             # POST /ingest (SSE), POST /ingest/reset, GET /ingest/status, GET /changes
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
│   │   ├── askflow/                  # Ask pipeline: intent.py (rules), queries.py (Cypher), assemble.py (pure), pipeline.py (events)
│   │   └── ingest/
│   │       ├── decisions_extractor.py# Decision extraction & verb-based status derivation
│   │       ├── live.py               # Live ingest pipeline, diff, reset, change log
│   │       ├── source_text.py        # Source bodies, quote matching
│   │       ├── notes_source.py       # Meeting notes ingestion parser
│   │       ├── tickets_source.py     # Tickets ingestion parser
│   │       └── sql_source.py         # Relational entities ingestion parser
│   └── tests/                        # 110 unit tests + 17 integration tests (pytest -m integration); fixtures/askflow_live_rows.json
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
│   ├── e2e/                          # Playwright: app, ingest, ask-stream (Phase 3), design-compare
│   └── screenshots/                  # ask/decisions/graph at 1440 and 390, plus compare-*.png
└── scripts/
    ├── evaluate.py                   # Scores the live graph against data/GROUND_TRUTH.md (read-only)
    ├── evaluate_holdout.py           # Cold extraction on data/holdout (own dataset)
    ├── evaluate_holdout2.py          # Cold extraction on data/holdout2 (own dataset)
    ├── split_composites.py           # Splits list-valued Person/System nodes (idempotent)
    ├── backfill_source_text.py       # Adds source bodies + per-source quotes in place (idempotent)
    ├── capture_fixtures.py           # Refreshes frontend/src/mocks from the current backend + graph
    ├── restore_snapshot.py           # export (safe) / restore (DELETES ALL GRAPHS; guarded)
    ├── seed.py                       # Full pipeline (DELETES ALL GRAPHS first; guarded)
    ├── destructive_guard.py          # Flag + production refusal + typed confirmation for the two above
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

## 9b. MCP server and agent access (Phase 4)

* `backend/app/mcp_server.py`: official `mcp` SDK (`FastMCP`, pinned `<2`; declared in `backend/requirements-mcp.txt` and installed in its own Dockerfile layer, because editing `pyproject.toml` invalidates the large cached dependency layer and the cold install exceeded Railway's 10-minute build limit; `pip install -r requirements-mcp.txt` for local runs), Streamable HTTP, stateless, served at `/mcp` by the FastAPI app itself (routes appended in `server.py`; DNS-rebinding protection off because the host is public). The session manager runs in its own task in `server.lifespan` (anyio requires enter/exit in one task and `main.py` starts/stops the lifespan from different ones).
* Tools, all thin wrappers: `ask`, `get_decision`, `list_decisions`, `impact_of`, `who_knows` (these three reuse the Ask pipeline), `find_conflicts` (health map + contradicts edges + orphaned systems, no LLM), `add_source` (live ingest: `INGEST_LOCK`, 3/min limit, auto-reset; disabled with `MCP_READ_ONLY=true`). Every call is rate limited per IP (`check_rate_limits`) and recorded in the `/changes` feed as `kind: "agent"`.
* `GET /attention` (`api/attention.py`): conflicts, orphaned systems, possibly stale decisions, superseded decisions whose systems have tickets opened after the replacement. Whitelisted in the Cloudflare proxy.
* Intent fallback (`askflow/intent.py`): rules first; only when none match, one cached model call returns `{intent, entity}` (shown as "· by model" in the understanding step). A failing call leaves the question as `other`.
* `scripts/mcp_smoke.py [URL]` connects with the official client, lists tools, calls every read tool and asserts the benchmark answers; `deploy-backend.yml` runs it against production after each deploy.
* Client snippets (verified against official docs): Claude Code `claude mcp add --transport http` (code.claude.com/docs/en/mcp), Claude Desktop `npx -y mcp-remote <url> --transport http-only` in `claude_desktop_config.json` (modelcontextprotocol.io connect-local-servers + github.com/geelen/mcp-remote), Cursor `{"mcpServers": {name: {"url": ...}}}` in `.cursor/mcp.json` (cursor.com/docs/context/mcp).

---

## 9c. Hardening (Phase 5, feature freeze)

* **Timeouts**: every Cypher statement is bounded (`QUERY_TIMEOUT_MS` 15 s on the server, 20 s caller wait, `memory.query_graph`, which now always runs in a worker thread); LLM calls 45 s (intent fallback 12 s); the frontend `apiFetch` times plain requests out at 25 s and streams stall out after 60 s without data; the Cloudflare proxy gives plain requests 30 s and the two streams 170 s and answers 502/504 JSON when Railway is down or slow.
* **Daily LLM budget**: `LLM_DAILY_TOKEN_BUDGET` (default 300000 estimated tokens, prompt + answer at 4 chars per token, 0 = unlimited) is counted across Ask, intent fallback and ingest (`api/rate_limiter.py`, logger `decision_trace.usage`). Over budget: Ask serves a saved answer for a repeated question or ends with a `demo_limit` error ("Demo limit reached..."), `POST /ingest` and `add_source` answer 429. The old 500 calls/day global cap and per-IP limits (Ask 20/min and 200/day, ingest 3/min) still apply.
* **Read caching**: list and detail endpoints are cached for 2 minutes per argument set with single-flight (`cache.cached_endpoint`); ingest, reset and auto-reset call `cache.invalidate()`.
* **Change feed**: CI smoke calls send `X-DT-Smoke: 1`, are stored with type `smoke` and hidden from `/changes` unless `include_tests=true`. `scripts/cleanup_agent_changes.py [--delete]` lists/removes MCP agent entries.
* **Data fix**: the generator wrote ticket dates like `2026-002-14`; fixed in `generate_synthetic_dataset.py`, `data/tickets.csv`, the snapshot, the live graph and the Explore mock. Nothing is dated after 2026-10-18.
* **Ingest lock**: check-and-acquire is atomic inside the stream, so a request that loses the race gets an `error` event ("Another ingest or reset is running") instead of queueing.
* **First impression**: per-route tab titles (`utils/pageTitle.ts`), favicon, Open Graph/Twitter tags with `public/og.png` (1200x630), a "What is this?" intro on Home, Sources and Agents in the sidebar, a real 404 page.
* **Tools**: `scripts/load_test.py` (concurrent Ask streams, page loads, MCP sessions, rate-limit check) and `scripts/live_walkthrough.mjs` (fresh-browser judge walkthrough at 1440 and 390 with screenshots).

---

## 10. Open Items

1. **Orphaned Elasticsearch has no decision in the corpus** (see 3C). If a stale-by-departed-decider demo is wanted, add a source document in which a departed person decides something; do not edit extraction to invent one.
2. The FalkorDB keepalive workflow fails: the repo's Actions secrets lack the FalkorDB credentials it reads.
3. The intent classifier is rule-based. Phrasings outside its patterns fall back to the why retrieval, which still answers but without impact or expertise sections.

## 11. Submission package (Phase 6)

* Repository history was rewritten once (git filter-repo) to remove two API keys that early commits had hard-coded as `os.getenv` defaults (`backend/app/config.py`, `backend/app/brain/memory.py`); the keys must be treated as compromised and rotated. A full-history `gitleaks` scan now reports no leaks.
* `README.md` is the judge-facing document (links, track mapping, architecture, schema and Cypher, evaluation, run-locally steps verified from a fresh clone against a throwaway local FalkorDB container). `LICENSE` is MIT. `.env.example` lists every variable; optional ones are commented out because an empty value is read as "set to empty".
* Local setup needs two installs: `backend/pyproject.toml` (Docker caches that layer) and `backend/requirements-mcp.txt`; `boto3` is only needed for Amazon Bedrock. The Vite dev server now uses port 5173 to match the backend's default CORS origin.


## 12. Landing, organizations, upload, GitHub import, company map (Phase 7)

* **Routing.** `/` is the landing page (`pages/LandingPage.tsx`, screenshots in `public/landing/`); the app lives under `/app/*` (sample organization) and `/app/o/:org/*` (user organizations). Old URLs (`/decisions/DEC-11`, `/graph?node=`) redirect to their `/app` equivalents. Pages keep writing `/decisions/...`: `src/router.tsx` re-exports `Link`, `NavLink`, `Navigate`, `useNavigate` and `useLocation` and adds/strips the app base (`org/orgState.ts`); import router pieces from there, not from `react-router-dom`.
* **Organizations.** `backend/app/orgs/registry.py` keeps the registry in its own graph `dt_registry` (`:Org {id,name,graph_name,created_at,last_active,source_count}`) and in memory; the sample is virtual (the configured production graph). `orgs/middleware.py` rewrites `/orgs/<id>/<path>` to `/<path>` and sets `brain/orgctx.py` context variables; `memory.resolve_active_graph_name` returns the org graph for the default dataset, `cache.py` keys every entry by graph, `INGEST_LOCK` is per graph (`ScopedLock`), and the Ask answer cache is keyed by graph. `memory.run_on_graph`/`delete_graph` use a plain FalkorDB client (no Cognee) for registry work. `api/orgs.py`: `POST /orgs` (3/h/IP, max 25), `GET`/`DELETE /orgs/{id}`. Idle organizations (72 h) are deleted by `registry.idle_loop` (hourly, never the sample). User organizations keep their data: `/ingest/reset` is 403 and `/ingest/status` reports no demo data. MCP tools take an optional `org`. Frontend: `components/org/` (switcher, new organization, settings/delete), `org/OrgLayout.tsx`, query keys end with the organization. The Cloudflare proxy whitelists `POST /orgs`, `GET|DELETE /orgs/:id`, and every whitelisted route under `/orgs/:id/`.
* **Upload.** `POST /ingest/batch` (`ingest/batch.py`): files with text or `pdf_base64` (pypdf, `requirements-mcp.txt`), type auto-detected, long files chunked in `run_ingest` (4,500 characters), per-file `file` events plus `step`/`graph` events tagged with `file`, one merged `diff`. Frontend: `components/ingest/UploadPanel.tsx`, `utils/uploadFiles.ts`.
* **GitHub import.** `POST /ingest/github` (`ingest/github.py`), user organizations only. Parsing is deterministic (`parse_adr`, `supersession_pairs`); the model only names systems per ADR and judges PRs/issues, capped at 80,000 estimated tokens per import. Events: `progress`, then `diff` (with an `import` stats object) or `error`. A repository can be imported once per organization.
* **Ask over documents.** The why-query now also reads `Document` sources, and a source counts as cited when the answer names a decision (DEC-nn) that is based on it, so ADRs and uploaded documents get citations.
* **Company map.** `pages/GraphPage.tsx` (default map, `?node=` or the Focus button for the neighbourhood view), `components/CompanyMap.tsx`, `utils/companyMap.ts`. Tickets are hidden by default (`hide` URL parameter; `hide=none` shows everything).
* **Flags.** `src/config/features.ts` switches upload and GitHub off without removing code.
* **Tests.** `tests/test_orgs.py`, `test_batch.py`, `test_github_import.py`; `tests/test_orgs_integration.py` (live: create, upload two files, ask, sample untouched, delete); Playwright `landing`, `orgs`, `upload`, `github`, `map`.

## 13. Showcase organization and owner keys (Phase 8)

* **Sample organizations.** Acme (the configured graph, id `sample`) and any registry record with `sample: true` (today `arachne`, "Arachne (real GitHub ADRs)") behave the same: shared, read-only apart from tagged demo ingests, reset by `auto_reset_loop` (it visits every sample organization), never deleted, no settings. `orgctx.is_user_org()` is true only inside an organization somebody created; use it, not `current_graph()`, to decide user-versus-sample behaviour. `GET /orgs` lists the showcase organizations for the menu. Create or replace the showcase with `PYTHONPATH=backend python scripts/create_showcase_org.py [--recreate]` (imports the repo, un-tags everything so the demo reset keeps it, drops its change log). The registry reloads from FalkorDB at most every 2 minutes, so a script-made change shows up in the running app by itself.
* **Owner keys.** `POST /orgs` returns `owner_key` once; only `sha256` is stored (`owner_hash` on the `:Org` node). `api/orgs.require_owner` guards `POST /ingest`, `/ingest/batch` and `/ingest/github` in user organizations, and `DELETE /orgs/{id}` checks the key; header `X-Org-Key`. Organizations without a hash are view-only. MCP `add_source` into a user organization needs `owner_key`. Frontend: the key lives in localStorage next to the organization (`org/orgStore.ts`), `useOrgAccess()` gives `{isSample, canWrite}`, and visitors without the key see a read-only note in the Add source drawer and the empty Home.
