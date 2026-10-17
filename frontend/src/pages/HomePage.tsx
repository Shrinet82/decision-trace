import React, { useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowUp, Bot, Download, PlayCircle } from 'lucide-react';
import { useAttention, useChanges, useDecisions, useGraph, usePeople, useSources, useSystems } from '../api/hooks';
import type { AttentionItem, ChangeEntry } from '../api/types';
import { ListSkeleton } from '../components/entity/EntityStates';
import { PageFrame } from '../components/PageFrame';
import { StatusIcon } from '../components/StatusIcon';
import { btnPrimary } from '../components/ui';
import { SUGGESTED_QUESTIONS } from '../config/questions';
import { formatRelative } from '../utils/format';
import { decisionHref, systemHref } from '../utils/links';
import type { StatusKind } from '../utils/model';

const ATTENTION_ICON: Record<AttentionItem['kind'], StatusKind> = {
  conflict: 'conflict',
  orphaned: 'stale',
  stale: 'stale',
  superseded: 'superseded',
};

function attentionHref(item: AttentionItem): string {
  if (item.system) return systemHref(item.system);
  return decisionHref(item.decision_code ?? '');
}

const CHANGE_ICON: Record<ChangeEntry['kind'], React.ReactNode> = {
  ingest: <Download className="h-3.5 w-3.5" aria-hidden="true" />,
  reset: <PlayCircle className="h-3.5 w-3.5" aria-hidden="true" />,
  agent: <Bot className="h-3.5 w-3.5" aria-hidden="true" />,
};
const CHANGE_LABEL: Record<ChangeEntry['kind'], string> = {
  ingest: 'Source added',
  reset: 'Demo reset',
  agent: 'Agent',
};

function changeText(c: ChangeEntry): string {
  if (c.kind === 'agent') return `${c.title}${c.summary ? ` · ${c.summary}` : ''}`;
  return c.kind === 'ingest' ? `${c.title}${c.summary ? ` · ${c.summary}` : ''}` : c.summary || c.title;
}

const Section: React.FC<{ id: string; title: string; children: React.ReactNode }> = ({ id, title, children }) => (
  <section aria-labelledby={id} className="flex flex-col gap-2">
    <h2 id={id} className="m-0 text-sm font-semibold">
      {title}
    </h2>
    {children}
  </section>
);

const Stat: React.FC<{ label: string; value: string | number | undefined; detail?: string }> = ({
  label,
  value,
  detail,
}) => (
  <div className="flex flex-col gap-0.5 rounded-panel border border-divider px-3 py-2">
    <dt className="text-xs text-muted">{label}</dt>
    <dd className="m-0 text-lg font-semibold tabular-nums">{value ?? '–'}</dd>
    {detail && <dd className="m-0 text-xs text-muted">{detail}</dd>}
  </div>
);

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [input, setInput] = useState('');

  const attention = useAttention();
  const changes = useChanges(8);
  const decisions = useDecisions();
  const people = usePeople();
  const systems = useSystems();
  const sources = useSources();
  const graph = useGraph();

  // Old shared links were /?q=...; the composer now lives at /ask
  const legacyQuestion = params.get('q');
  if (legacyQuestion) return <Navigate to={`/ask?q=${encodeURIComponent(legacyQuestion)}`} replace />;

  const ask = (raw: string) => {
    const q = raw.trim();
    if (q.length >= 2) navigate(`/ask?q=${encodeURIComponent(q)}`);
  };

  return (
    <PageFrame header={<h1 className="m-0 text-sm font-medium text-text">Home</h1>}>
      <div className="mx-auto flex max-w-[820px] flex-col gap-8 px-5 py-8 min-[900px]:px-10">
        <div className="flex flex-col gap-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask(input);
            }}
            className="flex items-center gap-2 rounded-[10px] border border-border bg-surface py-2 pl-3.5 pr-2 shadow-composer"
          >
            <label htmlFor="home-question" className="sr-only">
              Ask a question
            </label>
            <input
              id="home-question"
              type="text"
              value={input}
              maxLength={500}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask why a decision was made, what a change affects, or who knows a system"
              className="h-7 min-w-0 flex-1 border-0 bg-transparent text-base text-text outline-none placeholder:text-muted"
            />
            <button type="submit" disabled={input.trim().length < 2} className={btnPrimary}>
              <ArrowUp className="h-3.5 w-3.5 sm:hidden" aria-hidden="true" />
              <span className="max-sm:sr-only">Ask</span>
            </button>
          </form>
          <ul aria-label="Suggested questions" className="m-0 flex list-none flex-wrap gap-2 p-0">
            {SUGGESTED_QUESTIONS.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  onClick={() => ask(q)}
                  className="rounded-chip border border-border bg-surface px-3 py-1 text-left text-sm text-text-2 transition-colors hover:bg-subtle"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <Section id="stats-heading" title="The brain">
          <dl className="m-0 grid grid-cols-2 gap-2 min-[560px]:grid-cols-5">
            <Stat label="Decisions" value={decisions.data?.length} />
            <Stat label="People" value={people.data?.length} />
            <Stat label="Systems" value={systems.data?.length} />
            <Stat label="Sources" value={sources.data?.items.length} />
            <Stat
              label="Graph"
              value={graph.data ? `${graph.data.total_nodes} nodes` : undefined}
              detail={graph.data ? `${graph.data.total_edges} edges` : undefined}
            />
          </dl>
        </Section>

        <Section id="attention-heading" title="Needs attention">
          {attention.isLoading && <ListSkeleton label="Loading the attention queue" />}
          {attention.isError && (
            <p role="alert" className="m-0 text-status-conflict-text">
              {attention.error.message}
            </p>
          )}
          {attention.data && attention.data.items.length === 0 && (
            <p className="m-0 rounded-panel border border-divider bg-subtle px-4 py-5 text-muted">
              Nothing needs attention: no conflicts, no unowned systems, no stale decisions.
            </p>
          )}
          {attention.data && attention.data.items.length > 0 && (
            <ul className="m-0 list-none overflow-hidden rounded-panel border border-divider p-0">
              {attention.data.items.map((item) => (
                <li key={`${item.kind}-${item.decision_code ?? item.system}`}>
                  <Link
                    to={attentionHref(item)}
                    className="flex items-start gap-3 border-b border-row-divider px-4 py-2.5 last:border-b-0 hover:bg-subtle"
                  >
                    <span className="mt-0.5 inline-flex">
                      <StatusIcon status={ATTENTION_ICON[item.kind]} />
                    </span>
                    <span className="flex min-w-0 flex-col">
                      <span className="font-medium">{item.title}</span>
                      <span className="text-sm text-muted">{item.reason}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section id="changes-heading" title="Recent changes">
          {changes.isLoading && <ListSkeleton label="Loading recent changes" />}
          {changes.isError && (
            <p role="alert" className="m-0 text-status-conflict-text">
              {changes.error.message}
            </p>
          )}
          {changes.data && changes.data.length === 0 && (
            <p className="m-0 text-muted">No changes yet. Add a source or connect an agent.</p>
          )}
          {changes.data && changes.data.length > 0 && (
            <ul className="m-0 list-none p-0">
              {changes.data.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center gap-3 border-b border-row-divider py-2 last:border-b-0"
                >
                  <span className="inline-flex shrink-0 text-muted" title={CHANGE_LABEL[c.kind]}>
                    {CHANGE_ICON[c.kind]}
                    <span className="sr-only">{CHANGE_LABEL[c.kind]}</span>
                  </span>
                  <span className="min-w-0 flex-1 truncate">{changeText(c)}</span>
                  <time dateTime={c.created_at} className="shrink-0 text-xs text-muted">
                    {formatRelative(c.created_at)}
                  </time>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </PageFrame>
  );
};
