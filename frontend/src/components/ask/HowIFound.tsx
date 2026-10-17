import React from 'react';
import { Link } from 'react-router-dom';
import type { MatchedEntity } from '../../api/types';
import type { AskRunState } from '../../utils/askRun';
import { formatMs } from '../../utils/format';
import { decisionHref, personHref, systemHref } from '../../utils/links';
import { StepIcon } from '../ingest/StepList';
import { SystemSquare } from '../SystemMark';

const INTENT_LABEL: Record<string, string> = {
  why: 'Why / what replaced',
  impact: 'Impact of a change',
  expertise: 'Who knows about it',
  status: 'Health and ownership',
  other: 'General question',
};

const entityHref = (e: MatchedEntity) =>
  e.label === 'System' ? systemHref(e.name) : e.label === 'Person' ? personHref(e.name) : decisionHref(e.decision_code ?? e.id ?? e.name);

const EntityChip: React.FC<{ entity: MatchedEntity }> = ({ entity }) => (
  <Link
    to={entityHref(entity)}
    title={`${entity.label}: ${entity.name}`}
    className="inline-flex h-[22px] max-w-full items-center gap-1.5 rounded-chip border border-border bg-surface px-2 text-xs text-text-2 hover:bg-subtle"
  >
    {entity.label === 'System' && <SystemSquare system={entity.name} />}
    {entity.label === 'Decision' && entity.decision_code && (
      <span className="shrink-0 whitespace-nowrap font-medium text-accent">{entity.decision_code}</span>
    )}
    <span className="truncate">
      {entity.label === 'Decision' ? entity.name.split(' ').slice(0, 4).join(' ') + '…' : entity.name}
    </span>
  </Link>
);

/**
 * The live trace of one answer: each step with its time, the entities the question matched, and
 * every Cypher query (collapsible) with its row count. Total time at the bottom.
 */
export const HowIFound: React.FC<{
  run: AskRunState | null;
  headingLevel?: 'h2' | 'h3';
  /** Hide the visible title (the phone disclosure's summary already shows it). */
  showTitle?: boolean;
}> = ({ run, headingLevel: Heading = 'h2', showTitle = true }) => {
  if (!run) return null;
  const running = run.steps.find((s) => s.status === 'running');
  const finished = Boolean(run.result || run.error);

  return (
    <section aria-label="How I found this" className="flex min-w-0 flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <Heading className={showTitle ? 'm-0 text-sm font-semibold' : 'sr-only'}>How I found this</Heading>
        {run.intent && <span className="truncate text-xs text-muted">{INTENT_LABEL[run.intent]}</span>}
      </div>
      <p className="sr-only" aria-live="polite">
        {finished ? (run.error ? 'Failed' : 'Answer ready') : running ? running.label : ''}
      </p>
      <ol className="m-0 flex list-none flex-col p-0">
        {run.steps.map((s) => (
          <li
            key={s.key}
            data-ask-step={s.key}
            data-step-status={s.status}
            aria-current={s.status === 'running' ? 'step' : undefined}
            className="flex flex-col gap-1 border-b border-row-divider py-2 last:border-b-0"
          >
            <div className="flex items-start gap-2">
              <span className="mt-[2px] inline-flex shrink-0">
                <StepIcon status={s.status} />
              </span>
              <span className={`min-w-0 flex-1 ${s.status === 'pending' || s.status === 'skipped' ? 'text-muted' : 'text-text'}`}>
                {s.label}
              </span>
              {s.status !== 'pending' && s.status !== 'running' && s.ms !== undefined && (
                <span className="shrink-0 tabular-nums text-xs text-muted">{formatMs(s.ms)}</span>
              )}
            </div>
            {s.detail && <span className="pl-[22px] text-xs text-muted">{s.detail}</span>}
            {s.key === 'matching' && run.entities.length > 0 && (
              <ul aria-label="Matched entities" className="m-0 flex list-none flex-wrap gap-1 p-0 pl-[22px]">
                {run.entities.map((e) => (
                  <li key={`${e.label}:${e.id ?? e.name}`} className="min-w-0 max-w-full">
                    <EntityChip entity={e} />
                  </li>
                ))}
              </ul>
            )}
            {s.key === 'traversal' && run.queries.some((q) => q.step === 'traversal') && (
              <QueryList queries={run.queries.filter((q) => q.step === 'traversal')} />
            )}
            {s.key === 'matching' && run.queries.some((q) => q.step === 'matching') && (
              <QueryList queries={run.queries.filter((q) => q.step === 'matching')} />
            )}
          </li>
        ))}
      </ol>
      {run.totalMs !== null && (
        <div className="flex items-center justify-between border-t border-divider pt-2 text-xs">
          <span className="text-muted">Total</span>
          <span data-testid="ask-total-ms" className="font-medium tabular-nums">{formatMs(run.totalMs)}</span>
        </div>
      )}
    </section>
  );
};

const QueryList: React.FC<{ queries: AskRunState['queries'] }> = ({ queries }) => (
  <ul aria-label="Cypher queries" className="m-0 flex list-none flex-col gap-1 p-0 pl-[22px]">
    {queries.map((q, i) => (
      <li key={`${q.name}-${i}`}>
        <details className="group rounded-control border border-divider bg-subtle">
          <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-0.5 px-2 py-1 text-xs">
            <span aria-hidden="true" className="text-muted transition-transform group-open:rotate-90">›</span>
            <code className="whitespace-nowrap font-mono text-text-2">{q.name}</code>
            <span className="ml-auto whitespace-nowrap tabular-nums text-muted">
              {q.rows} {q.rows === 1 ? 'row' : 'rows'} · {formatMs(q.ms)}
            </span>
          </summary>
          <pre tabIndex={0} aria-label={`Cypher for ${q.name}`} className="m-0 max-h-56 overflow-auto whitespace-pre-wrap break-words border-t border-divider px-2 py-1.5 font-mono text-[11px] leading-[1.5] text-text-2">
            {q.query.replace(/ (OPTIONAL MATCH|MATCH|WITH|RETURN|UNWIND|WHERE|ORDER BY)\b/g, '\n$1')}
          </pre>
        </details>
      </li>
    ))}
  </ul>
);
