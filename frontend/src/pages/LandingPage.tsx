import React from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, Bot, GitBranch, Network, Plug } from 'lucide-react';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { StatusIcon } from '../components/StatusIcon';
import type { StatusKind } from '../utils/model';
import { MCP_TOOLS, MCP_URL } from '../config/mcp';

const REPO_URL = 'https://github.com/Shrinet82/decision-trace';
const DOCS_URL = `${REPO_URL}#readme`;

const askHref = (q: string) => `/app/ask?q=${encodeURIComponent(q)}`;

/** One real answer from the Acme sample: DEC-11 and the path behind it. */
const HERO_QUESTION = 'Why did we move sessions to Keycloak?';

interface PathRow {
  kind: string;
  code?: string;
  title: string;
  status?: StatusKind;
  /** The edge that leads from this row to the next one. */
  edge?: string;
}

const HERO_PATH: PathRow[] = [
  { kind: 'Ticket', code: 'TICK-102', title: 'Redis session cluster operational maintenance and failover complexity', edge: 'based on' },
  { kind: 'Decision', code: 'DEC-11', title: 'Migrate session storage to embedded Keycloak cache', status: 'active', edge: 'supersedes' },
  { kind: 'Decision', code: 'DEC-01', title: 'Migrate session storage from Postgres to Redis cluster', status: 'superseded' },
];

/** Questions about relationships, each answered from the sample graph. */
const QUESTIONS: { q: string; status: StatusKind; answer: React.ReactNode }[] = [
  {
    q: 'Do any decisions conflict?',
    status: 'conflict',
    answer: (
      <>
        <b className="font-medium text-text">DEC-04</b> (Kafka for all event messaging, Alice Vance) contradicts{' '}
        <b className="font-medium text-text">DEC-07</b> (RabbitMQ for the same thing, Bob Martin). Nobody has reconciled them.
      </>
    ),
  },
  {
    q: 'Which systems have no owner?',
    status: 'stale',
    answer: (
      <>
        <b className="font-medium text-text">Elasticsearch.</b> Its owner, Marcus Aurelius, left on 30 November 2025, and
        nobody took it over.
      </>
    ),
  },
  {
    q: 'What’s affected if we drop Snowflake?',
    status: 'superseded',
    answer: (
      <>
        <b className="font-medium text-text">DEC-03</b>, which adopted it, was already superseded by DEC-13 (ClickHouse), and{' '}
        <b className="font-medium text-text">DEC-17</b> decommissions the warehouses. The answer also lists the people, teams and tickets to involve.
      </>
    ),
  },
];

const STEPS = [
  {
    icon: Plug,
    title: 'Connect sources',
    body: 'Upload meeting notes, tickets and ADRs, or import a public GitHub repository. Every file keeps its verbatim text.',
  },
  {
    icon: Network,
    title: 'The brain builds a graph in FalkorDB',
    body: 'Decisions, people, systems and the evidence behind them become nodes and edges. Supersession and conflicts are derived, not guessed.',
  },
  {
    icon: GitBranch,
    title: 'Ask, trace, stay current',
    body: 'Every answer shows the Cypher it ran and cites real source quotes. Add a source and see exactly what changed.',
  },
];

const primaryBtn =
  'inline-flex h-10 items-center gap-2 rounded-control bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
const secondaryBtn =
  'inline-flex h-10 items-center gap-2 rounded-control border border-border bg-surface px-4 text-sm font-medium text-text hover:bg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

const TraceCard: React.FC = () => (
  <figure className="m-0 overflow-hidden rounded-panel border border-border bg-surface text-left shadow-composer">
    <div className="border-b border-divider px-5 py-4">
      <p className="m-0 text-xs text-muted">Asked of the Acme sample</p>
      <p className="m-0 mt-1 text-lg font-semibold">{HERO_QUESTION}</p>
    </div>

    <div className="px-5 py-4">
      <div className="flex items-center gap-2 text-sm">
        <StatusIcon status="active" />
        <span className="font-medium text-text">Still valid</span>
        <span className="text-muted">· decided by Alice Vance, 12 May 2026</span>
      </div>
      <p className="m-0 mt-2 text-base text-text-2">
        Sessions moved to Keycloak&rsquo;s embedded cache to end the maintenance and failover burden of the Redis session
        cluster. That replaced the earlier move from Postgres to Redis.
      </p>

      <p className="m-0 mt-5 text-xs font-medium text-muted">Evidence path</p>
      <ol className="m-0 mt-2 list-none p-0">
        {HERO_PATH.map((row) => (
          <li key={row.code}>
            <div className="flex items-start gap-3 rounded-control border border-border bg-panel px-3 py-2">
              <span className="w-[60px] shrink-0 pt-px text-xs text-muted">{row.kind}</span>
              <span className="min-w-0 text-sm">
                <span className="mr-1.5 font-medium tabular-nums text-text">{row.code}</span>
                <span className={row.status === 'superseded' ? 'text-muted line-through' : 'text-text-2'}>{row.title}</span>
              </span>
              {row.status && <StatusIcon status={row.status} labelled className="ml-auto mt-0.5 shrink-0" />}
            </div>
            {row.edge && (
              <div className="ml-[38px] flex h-7 items-center gap-2 border-l border-border pl-3 text-xs text-muted">
                {row.edge}
              </div>
            )}
          </li>
        ))}
      </ol>

      <blockquote className="m-0 mt-5 border-l-2 border-accent pl-3">
        <p className="m-0 text-sm text-text">&ldquo;Alice Vance decided: Migrate session storage to embedded Keycloak cache.&rdquo;</p>
        <footer className="mt-1 text-xs text-muted">TICK-102, quoted verbatim on the based-on edge</footer>
      </blockquote>
    </div>

    <figcaption className="flex flex-wrap items-center justify-between gap-2 border-t border-divider bg-subtle px-5 py-3 text-xs text-muted">
      <span>Every step and Cypher query is listed under &ldquo;How I found this&rdquo;.</span>
      <Link to={askHref(HERO_QUESTION)} className="font-medium text-accent hover:underline">
        Run it live
      </Link>
    </figcaption>
  </figure>
);

export const LandingPage: React.FC = () => {
  useDocumentTitle(null);
  const [params] = useSearchParams();
  // Old Home links used /?q=...; they now live on the Ask page.
  const legacyQuestion = params.get('q');
  if (legacyQuestion) return <Navigate to={`/app/ask?q=${encodeURIComponent(legacyQuestion)}`} replace />;

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="mx-auto flex h-14 max-w-[1120px] items-center justify-between px-4 min-[900px]:px-6">
        <Link to="/" className="flex items-center gap-2 text-text no-underline">
          <span
            aria-hidden="true"
            className="flex h-5 w-5 items-center justify-center rounded-[5px] bg-accent text-[11px] font-semibold text-white"
          >
            DT
          </span>
          <span className="text-sm font-semibold">Decision Trace</span>
        </Link>
        <nav aria-label="Site" className="flex items-center gap-4 text-sm">
          <a href={DOCS_URL} className="text-text-2 hover:text-text">Docs</a>
          <a href={REPO_URL} className="hidden text-text-2 hover:text-text min-[480px]:inline">GitHub</a>
          <Link to="/app" className="font-medium text-accent hover:underline">Open the app</Link>
        </nav>
      </header>

      <main id="main-content">
        <section className="mx-auto grid max-w-[1120px] items-center gap-10 px-4 pb-16 pt-10 min-[900px]:px-6 min-[1000px]:grid-cols-[5fr_6fr] min-[1000px]:gap-14 min-[1000px]:pt-20">
          <div>
            <p className="m-0 mb-4 text-xs font-medium uppercase tracking-wider text-muted">The company brain for decisions</p>
            <h1 className="m-0 text-[32px] font-semibold leading-[1.1] tracking-tight min-[900px]:text-[48px]">
              Ask why any decision was made.
            </h1>
            <p className="m-0 mt-5 max-w-[480px] text-[16px] leading-[1.6] text-text-2">
              Decision Trace reads your meeting notes, tickets and ADRs into a FalkorDB graph. Ask it who decided, what
              the decision rests on, and whether it still holds. Every answer quotes its source.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/app" className={primaryBtn}>
                Try the product <ArrowRight size={15} aria-hidden="true" />
              </Link>
              <Link to="/app/agents" className={secondaryBtn}>
                <Bot size={15} aria-hidden="true" /> Connect an agent
              </Link>
            </div>
            <p className="m-0 mt-6 text-sm text-muted">
              No sign-up. The sample company is already loaded: 17 decisions, 146 nodes, 374 edges.
            </p>
          </div>
          <TraceCard />
        </section>

        <section aria-labelledby="questions" className="border-y border-border bg-surface">
          <div className="mx-auto max-w-[1120px] px-4 py-16 min-[900px]:px-6">
            <h2 id="questions" className="m-0 text-[22px] font-semibold tracking-tight">
              Questions search can&rsquo;t answer
            </h2>
            <p className="m-0 mt-2 max-w-[600px] text-base text-text-2">
              Search finds documents. These are questions about how decisions, people and systems relate, so the graph
              answers them. Here is what it says about the sample company.
            </p>
            <ul className="m-0 mt-8 grid list-none grid-cols-1 gap-x-10 gap-y-8 p-0 min-[900px]:grid-cols-3">
              {QUESTIONS.map((item) => (
                <li key={item.q} className="border-t border-border pt-4">
                  <Link to={askHref(item.q)} className="group flex items-start gap-2 text-lg font-semibold text-text">
                    <StatusIcon status={item.status} className="mt-[3px] shrink-0" />
                    <span className="group-hover:underline">{item.q}</span>
                  </Link>
                  <p className="m-0 mt-2 text-base text-text-2">{item.answer}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="how" className="mx-auto max-w-[1120px] px-4 py-16 min-[900px]:px-6">
          <h2 id="how" className="m-0 text-[22px] font-semibold tracking-tight">How it works</h2>
          <ol className="m-0 mt-8 grid list-none grid-cols-1 gap-8 p-0 min-[900px]:grid-cols-3 min-[900px]:gap-10">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <div className="mb-3 flex items-center gap-2 text-xs font-medium text-muted">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent-ring text-accent">
                    <s.icon size={13} aria-hidden="true" />
                  </span>
                  Step {i + 1}
                </div>
                <h3 className="m-0 text-lg font-semibold">{s.title}</h3>
                <p className="m-0 mt-2 text-base text-text-2">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="map" className="mx-auto max-w-[1120px] px-4 pb-16 min-[900px]:px-6">
          <div className="flex flex-col gap-2 min-[900px]:flex-row min-[900px]:items-end min-[900px]:justify-between">
            <div>
              <h2 id="map" className="m-0 text-[22px] font-semibold tracking-tight">The company map</h2>
              <p className="m-0 mt-2 max-w-[600px] text-base text-text-2">
                The whole graph at a glance: colour by type, size by connections, health on every decision. Click a node
                to light up its neighbours.
              </p>
            </div>
            <Link to="/app/explore" className="text-sm font-medium text-accent hover:underline">
              Open the map
            </Link>
          </div>
          <div className="mt-6 overflow-hidden rounded-panel border border-border bg-surface shadow-composer">
            <img
              src="/landing/map.png"
              alt="The Explore page showing the company graph with a decision selected"
              width={1440}
              height={900}
              loading="lazy"
              className="block h-auto w-full"
            />
          </div>
        </section>

        <section aria-label="Go further" className="mx-auto max-w-[1120px] px-4 pb-16 min-[900px]:px-6">
          <div className="grid grid-cols-1 gap-4 min-[900px]:grid-cols-2">
            <div className="flex flex-col rounded-panel border border-border bg-surface p-6">
              <h2 className="m-0 text-xl font-semibold">Give your agent the same answers</h2>
              <p className="m-0 mt-2 text-base text-text-2">
                One MCP endpoint for Claude, Cursor or any MCP client. No sign-in needed.
              </p>
              <code className="mt-4 block break-all rounded-control border border-border bg-subtle px-3 py-2 font-mono text-xs text-text">
                {MCP_URL}
              </code>
              <ul className="m-0 mt-3 flex list-none flex-wrap gap-1.5 p-0" aria-label="Tools">
                {MCP_TOOLS.map((t) => (
                  <li key={t.name} className="rounded-chip border border-border px-2 py-0.5 font-mono text-xs text-text-2">
                    {t.name}
                  </li>
                ))}
              </ul>
              <div className="mt-auto pt-6">
                <Link to="/app/agents" className={secondaryBtn}>
                  Set up an agent <ArrowRight size={15} aria-hidden="true" />
                </Link>
              </div>
            </div>

            <div className="flex flex-col rounded-panel border border-border bg-surface p-6">
              <h2 className="m-0 text-xl font-semibold">See it on a real open-source repo</h2>
              <p className="m-0 mt-2 text-base text-text-2">
                The Arachne framework&rsquo;s architecture decision records, imported straight from GitHub: 16 ADRs, who
                wrote them, which ones supersede others, every decision traced to its source file. Nothing here was
                written for the demo.
              </p>
              <div className="mt-auto pt-6">
                <Link to="/app/o/arachne" className={secondaryBtn}>
                  Open the Arachne organization <ArrowRight size={15} aria-hidden="true" />
                </Link>
              </div>
            </div>
          </div>
        </section>

        <section className="border-t border-border bg-surface">
          <div className="mx-auto flex max-w-[1120px] flex-col gap-4 px-4 py-12 min-[900px]:flex-row min-[900px]:items-center min-[900px]:justify-between min-[900px]:px-6">
            <div>
              <h2 className="m-0 text-xl font-semibold">Start with a question</h2>
              <p className="m-0 mt-1 text-base text-text-2">
                The sample company has 17 decisions, 2 conflicts and one system nobody owns. Or start an empty
                organization and add your own sources.
              </p>
            </div>
            <Link to="/app" className={`${primaryBtn} self-start min-[900px]:self-auto`}>
              Try the product <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1120px] flex-col gap-3 px-4 py-6 text-sm text-muted min-[900px]:flex-row min-[900px]:items-center min-[900px]:justify-between min-[900px]:px-6">
          <p className="m-0">
            Built for the FalkorDB Graph Hacks, Track 03: Company Brain. Every query runs on{' '}
            <a href="https://www.falkordb.com/" className="text-accent underline">FalkorDB</a>.
          </p>
          <div className="flex gap-4">
            <a href={REPO_URL} className="text-text-2 hover:text-text">GitHub</a>
            <a href={DOCS_URL} className="text-text-2 hover:text-text">Docs</a>
            <Link to="/app/agents" className="text-text-2 hover:text-text">Connect an agent</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
