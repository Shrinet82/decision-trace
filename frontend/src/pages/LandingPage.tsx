import React from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, Bot, GitBranch, Network, Plug } from 'lucide-react';
import { useDocumentTitle } from '../hooks/useDocumentTitle';

const REPO_URL = 'https://github.com/Shrinet82/decision-trace';
const DOCS_URL = `${REPO_URL}#readme`;

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

const FEATURES = [
  {
    title: 'Ask why, and see how it was found',
    body: 'Streamed answers with an evidence path from the decision back to the ticket or meeting it came from. "How I found this" lists every step and every Cypher query with its timing.',
    image: '/landing/ask.png',
    alt: 'The Ask page answering why sessions moved to Keycloak, with the evidence path and the How I found this panel',
  },
  {
    title: 'Decision lineage you can follow',
    body: 'Each decision page shows what it replaced, what replaced it, what contradicts it, who decided, and whether the decider is still on the team.',
    image: '/landing/lineage.png',
    alt: 'A decision page with its lineage graph, sources with quotes and validity checks',
  },
  {
    title: 'Add a source, see the diff',
    body: 'Drop in a note and watch the brain read, extract, match and link it. The result is a change diff: new decisions, new conflicts, decisions that went stale.',
    image: '/landing/ingest.png',
    alt: 'The Add source drawer showing the change diff after an ingest',
  },
  {
    title: 'The company map',
    body: 'The whole graph at a glance: colour by type, size by connections, health overlaid. Click anything to light up its neighbours.',
    image: '/landing/map.png',
    alt: 'The Explore page showing the company graph with a decision selected',
  },
];

const primaryBtn =
  'inline-flex h-10 items-center gap-2 rounded-control bg-accent px-4 text-sm font-medium text-white hover:bg-accent-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
const secondaryBtn =
  'inline-flex h-10 items-center gap-2 rounded-control border border-border bg-surface px-4 text-sm font-medium text-text hover:bg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';

export const LandingPage: React.FC = () => {
  useDocumentTitle(null);
  const [params] = useSearchParams();
  // Old Home links used /?q=...; they now live on the Ask page.
  const legacyQuestion = params.get('q');
  if (legacyQuestion) return <Navigate to={`/app/ask?q=${encodeURIComponent(legacyQuestion)}`} replace />;

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="mx-auto flex h-14 max-w-[1080px] items-center justify-between px-4 min-[900px]:px-6">
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
        <section className="mx-auto max-w-[1080px] px-4 pb-12 pt-12 text-center min-[900px]:px-6 min-[900px]:pt-20">
          <p className="mb-4 text-xs font-medium uppercase tracking-wider text-muted">The company brain for decisions</p>
          <h1 className="mx-auto max-w-[760px] text-[28px] font-semibold leading-[1.15] tracking-tight min-[900px]:text-[44px]">
            Ask why any decision was made — who decided, what it&rsquo;s based on, and whether it still holds.
          </h1>
          <p className="mx-auto mt-5 max-w-[600px] text-base text-text-2">
            Decision Trace turns meeting notes, tickets and ADRs into a graph, then answers with the evidence path
            and the exact quotes behind it.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link to="/app" className={primaryBtn}>
              Try the product <ArrowRight size={15} aria-hidden="true" />
            </Link>
            <Link to="/app/agents" className={secondaryBtn}>
              <Bot size={15} aria-hidden="true" /> Connect an agent
            </Link>
          </div>
          <div className="mx-auto mt-12 max-w-[960px] overflow-hidden rounded-panel border border-border bg-surface shadow-composer">
            <img
              src="/landing/ask.png"
              alt="The Ask page answering why sessions moved to Keycloak, with the evidence path and the How I found this panel"
              width={1440}
              height={1176}
              className="block h-auto w-full"
            />
          </div>
        </section>

        <section aria-labelledby="how" className="border-y border-border bg-sidebar">
          <div className="mx-auto max-w-[1080px] px-4 py-14 min-[900px]:px-6">
            <h2 id="how" className="text-xl font-semibold">How it works</h2>
            <ol className="m-0 mt-6 grid list-none grid-cols-1 gap-4 p-0 min-[900px]:grid-cols-3">
              {STEPS.map((s, i) => (
                <li key={s.title} className="rounded-panel border border-border bg-surface p-5">
                  <div className="mb-3 flex items-center gap-2 text-xs font-medium text-muted">
                    <s.icon size={15} aria-hidden="true" className="text-accent" />
                    Step {i + 1}
                  </div>
                  <h3 className="text-lg font-semibold">{s.title}</h3>
                  <p className="mt-2 text-sm text-text-2">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section aria-label="Features" className="mx-auto max-w-[1080px] px-4 py-14 min-[900px]:px-6">
          <div className="flex flex-col gap-16">
            {FEATURES.map((f, i) => (
              <div
                key={f.title}
                className={`grid items-center gap-6 min-[900px]:grid-cols-[2fr_3fr] min-[900px]:gap-10 ${
                  i % 2 === 1 ? 'min-[900px]:[&>div:first-child]:order-2' : ''
                }`}
              >
                <div>
                  <h2 className="text-xl font-semibold">{f.title}</h2>
                  <p className="mt-3 text-base text-text-2">{f.body}</p>
                </div>
                <div className="overflow-hidden rounded-panel border border-border bg-surface shadow-composer">
                  <img src={f.image} alt={f.alt} loading="lazy" className="block h-auto w-full" />
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-[1080px] px-4 pb-16 min-[900px]:px-6">
          <div className="rounded-panel border border-border bg-surface p-8 text-center">
            <h2 className="text-xl font-semibold">See it on a real graph</h2>
            <p className="mx-auto mt-2 max-w-[520px] text-base text-text-2">
              The sample organization is a company with 17 decisions, 2 conflicts and one system nobody owns.
              Or start an empty organization and add your own sources.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Link to="/app" className={primaryBtn}>
                Try the product <ArrowRight size={15} aria-hidden="true" />
              </Link>
              <Link to="/app/agents" className={secondaryBtn}>Connect an agent</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1080px] flex-col gap-3 px-4 py-6 text-sm text-muted min-[900px]:flex-row min-[900px]:items-center min-[900px]:justify-between min-[900px]:px-6">
          <p className="m-0">
            Built for the FalkorDB Graph Hacks, Track 03: Company Brain. Every query runs on{' '}
            <a href="https://www.falkordb.com/" className="text-accent hover:underline">FalkorDB</a>.
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
