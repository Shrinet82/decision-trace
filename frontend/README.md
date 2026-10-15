# Decision Trace Frontend

Web UI for Decision Trace — an interactive, evidence-grounded decision memory explorer designed for engineering leaders, system architects, and compliance auditors.

## Key Features

- **Ask Interface**: Query architectural decisions, system ownership, and replacements with natural language.
- **Evidence Path Graph**: Interactive Cytoscape graph using the London Underground transit map aesthetic:
  - Left-to-right orthogonal layout (`dagre`).
  - Distinct node glyphs (Decision station markers, System rectangles, Person chips, Ticket documents).
  - Transit category lines (Messaging, Identity & Security, Data, Observability, Platform).
  - Supersedes (solid replacement) and Contradicts (dashed conflict) edge styling.
- **Accessible Path as List**: Full WCAG AA keyboard-accessible alternative view for every graph path.
- **Evidence Source Drawer**: Slide-over panel displaying source tickets and meeting notes, record metadata, and verbatim rationales.
- **Dual Theme Support**: Light and dark themes tuned for minimum 4.5:1 WCAG AA contrast ratio.
- **Standalone Mock Mode**: Preloaded with 5 frozen benchmark questions and 2 unanswerable sanity queries so reviewers can explore the complete application without spinning up backend or database services.

## Architecture & Topology

### 1. Frontend on Cloudflare Pages
The frontend is compiled into a static Single Page Application (`dist/`) and is pre-configured with `public/_redirects` for SPA routing on Cloudflare Pages:
- **Zero Config CI/CD**: Connect the GitHub repository to Cloudflare Pages. Every `git push` or pull request automatically generates a preview deployment with a live public URL.
- **Standalone Verification**: Because `VITE_USE_MOCKS` defaults to `true`, Cloudflare Pages builds allow anyone to click through the 5 benchmark questions, inspect Cytoscape graphs, and test drawers immediately on the web.

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
- **Styling**: Tailwind CSS, Overpass & Overpass Mono typography (`@fontsource`)
- **Graph Visualization**: Cytoscape.js with `cytoscape-dagre`
- **Data Fetching**: `@tanstack/react-query`
- **Icons**: `lucide-react`
- **Testing**: Vitest, React Testing Library, Playwright, `@axe-core/playwright`
