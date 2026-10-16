import React from 'react';
import { Link } from 'react-router-dom';
import type { IngestDiff } from '../../api/types';
import { HEALTH_LABEL } from '../../utils/changes';
import { decisionHref, personHref, systemHref } from '../../utils/links';
import { healthToStatus } from '../../utils/model';
import { StatusIcon } from '../StatusIcon';

const RELATION_TEXT = {
  supersedes: 'supersedes',
  contradicts: 'contradicts',
  none: 'kept separate from',
} as const;

const DiffSection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section aria-label={title} className="flex flex-col gap-1.5 border-t border-divider px-3 py-2.5">
    <h4 className="m-0 text-xs font-medium text-muted">{title}</h4>
    <ul className="m-0 flex list-none flex-col gap-1.5 p-0">{children}</ul>
  </section>
);

const linkClass = 'font-medium text-accent hover:underline';

/** The final result of an ingest: what was added and what changed in the existing graph. */
export const DiffCard: React.FC<{ diff: IngestDiff; onNavigate?: () => void }> = ({ diff, onNavigate }) => {
  const decisions = diff.nodes_added.filter((n) => n.label === 'Decision');
  const others = diff.nodes_added.length - decisions.length;
  const nothingChanged =
    decisions.length +
      diff.status_changes.length +
      diff.person_changes.length +
      diff.orphan_changes.length +
      diff.links.length ===
    0;

  return (
    <div
      role="region"
      aria-label="Ingest result"
      data-testid="ingest-diff"
      className="flex flex-col rounded-panel border border-divider"
    >
      <div className="flex flex-col gap-0.5 px-3 py-2.5">
        <p className="m-0 font-medium text-text">{diff.summary}</p>
        <p className="m-0 text-xs text-muted">
          {diff.source.title} · {diff.nodes_added.length} {diff.nodes_added.length === 1 ? 'node' : 'nodes'} and{' '}
          {diff.edges_added.length} {diff.edges_added.length === 1 ? 'edge' : 'edges'} added
          {others > 0 && decisions.length > 0 ? ` (${others} besides decisions)` : ''}
        </p>
      </div>

      {decisions.length > 0 && (
        <DiffSection title="New decisions">
          {decisions.map((d) => (
            <li key={d.id} className="flex min-w-0 flex-wrap items-baseline gap-x-2">
              <Link to={decisionHref(d.decision_code ?? d.id)} onClick={onNavigate} className={linkClass}>
                {d.decision_code ?? 'New decision'}
              </Link>
              <span className="min-w-0 text-text-2">{d.name}</span>
            </li>
          ))}
        </DiffSection>
      )}

      {diff.status_changes.length > 0 && (
        <DiffSection title="Status changes">
          {diff.status_changes.map((c) => (
            <li key={c.id} className="flex flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Link to={decisionHref(c.decision_code || c.id)} onClick={onNavigate} className={linkClass}>
                  {c.decision_code || c.title}
                </Link>
                <span className="inline-flex items-center gap-1 text-text-2">
                  <StatusIcon status={healthToStatus(c.before)} size={12} />
                  {HEALTH_LABEL[c.before] ?? c.before}
                </span>
                <span className="text-muted">→</span>
                <span className="inline-flex items-center gap-1 font-medium text-text">
                  <StatusIcon status={healthToStatus(c.after)} size={12} />
                  {HEALTH_LABEL[c.after] ?? c.after}
                </span>
              </span>
              <span className="text-xs text-muted">{c.title}</span>
            </li>
          ))}
        </DiffSection>
      )}

      {diff.person_changes.length > 0 && (
        <DiffSection title="People">
          {diff.person_changes.map((c) => (
            <li key={`${c.name}-${c.field}`} className="flex flex-wrap items-center gap-x-1.5">
              <Link to={personHref(c.name)} onClick={onNavigate} className={linkClass}>
                {c.name}
              </Link>
              <span className="text-text-2">
                : {c.before ? 'left company' : 'active'} → {c.after ? 'left company' : 'active'}
              </span>
            </li>
          ))}
        </DiffSection>
      )}

      {diff.orphan_changes.length > 0 && (
        <DiffSection title="Orphaned systems">
          {diff.orphan_changes.map((c) => (
            <li key={c.system} className="flex flex-wrap items-center gap-x-1.5">
              <Link to={systemHref(c.system)} onClick={onNavigate} className={linkClass}>
                {c.system}
              </Link>
              <span className="text-text-2">
                : {c.before ? 'orphaned' : 'owned'} → {c.after ? 'orphaned' : 'owned'}
              </span>
            </li>
          ))}
        </DiffSection>
      )}

      {diff.links.length > 0 && (
        <DiffSection title="Links the judge made">
          {diff.links.map((l) => (
            <li key={`${l.new_code}-${l.existing_code}`} className="flex flex-col gap-0.5">
              <span className="flex flex-wrap items-baseline gap-x-1.5">
                <Link to={decisionHref(l.new_code)} onClick={onNavigate} className={linkClass}>
                  {l.new_code}
                </Link>
                <span className="text-text-2">{RELATION_TEXT[l.relation] ?? l.relation}</span>
                <Link to={decisionHref(l.existing_code)} onClick={onNavigate} className={linkClass}>
                  {l.existing_code}
                </Link>
              </span>
              {l.reason && <span className="text-xs text-muted">{l.reason}</span>}
            </li>
          ))}
        </DiffSection>
      )}

      {nothingChanged && (
        <p className="m-0 border-t border-divider px-3 py-2.5 text-muted">
          No decisions, statuses, people or systems changed.
        </p>
      )}
    </div>
  );
};
