# Decision Trace Frontend

Web UI for Decision Trace — an interactive, evidence-grounded decision memory explorer designed for engineering leaders, system architects, and compliance auditors.

## Key Features

- **Ask**: A chat thread. Each answer shows a validity verdict, the answer text with numbered citation markers, a vertical **evidence path** around the primary decision, and source cards with the verbatim evidence quote. A properties panel shows the decision's status, deciders, system, supersedes/conflicts and validity checks. Unanswerable questions show a "No decision found" empty state with no evidence or citations.
- **Decision pages** (`/decisions/:code`): lineage graph (sources, supersedes chain both ways, conflicts), system timeline, sources with quotes, impact, and the exact Cypher used.
- **Systems and People**: list and detail pages with ownership, orphaned systems and departed people flagged.
- **Decisions**: Decisions grouped by status (Conflict, Possibly stale, Active, Superseded), each with a stable `DEC-NN` code, a relation hint, system chip, decider avatar and date. Tabs, filter, display options, and a peek panel.
- **Explore**: A Cytoscape explorer centred on one node (radial layout) with node-type filters showing real counts, Expand / Fit / Copy Cypher, and an inspector listing properties and edges.
- **Command palette**: `Cmd/Ctrl+K` searches decisions or asks a question.
- **Accessible**: Keyboard-reachable controls, visible focus rings, an `axe` check on every page at desktop and mobile widths, and a screen-reader node list for the graph canvas.
- **Standalone mock mode**: Frozen API responses (`src/mocks/`, captured from the live backend) let reviewers click through every page without any backend.

The design is a light-only, Linear-style system (Geist, 13px base). The static design mockups live in `design-ref/`; `e2e/design-compare.spec.ts` renders them next to the app into `screenshots/compare-*.png`.

## Architecture & Topology

### 1. Frontend on Cloudflare Pages
The frontend is compiled into a static Single Page Application (`dist/`) and is pre-configured with `public/_redirects` for SPA routing on Cloudflare Pages:
- **Zero Config CI/CD**: Deploy `dist/` to Cloudflare Pages (`wrangler pages deploy dist`). `functions/api/[[path]].ts` is the hardened reverse proxy to the backend.
- **Standalone Verification**: Because `VITE_USE_MOCKS` defaults to `true`, Cloudflare Pages builds allow anyone to click through the benchmark questions, inspect the graph, and explore the Ask, Decisions and Graph pages immediately on the web.

### 2. Full-Stack Topology
- **Frontend**: Cloudflare Pages (global edge CDN).
- **Backend**: FastAPI Python container (deployed on Cloud Run, Fly.io, Railway, or AWS ECS) with access to AWS Bedrock.
- **Database**: FalkorDB instance (Docker container or FalkorDB Cloud).
- **Edge Routing**: If deploying both, Cloudflare Pages can proxy `/api/*` requests to the backend container via Cloudflare redirects (`/api/* https://api.yourdomain.com/:splat 200`), eliminating CORS overhead.

## Setup & Development

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start local development server (http://localhost:5173)
npm run dev

# Run unit and integration tests (Vitest)
npm run test

# Run ESLint validation
npm run lint

# Build production bundle
npm run build

# Run local preview server (http://localhost:4173)
npm run preview

# Run end-to-end Playwright tests & axe-core accessibility checks
npm run test:e2e
```

## Environment Configuration

Create a `.env` file or configure build environment variables:

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Target URL for the Decision Trace FastAPI backend. |
| `VITE_USE_MOCKS` | `true` | When `true`, uses frozen benchmark responses (`src/mocks/`). Set to `false` when connecting to a live backend. |

## Library Credits

- **Framework**: React 18, Vite 6, TypeScript 5
- **Styling**: Tailwind CSS, Geist typography (Google Fonts)
- **Graph Visualization**: Cytoscape.js (radial `breadthfirst` layout)
- **Data Fetching**: `@tanstack/react-query`
- **Icons**: `lucide-react`
- **Testing**: Vitest, React Testing Library, Playwright, `@axe-core/playwright`
