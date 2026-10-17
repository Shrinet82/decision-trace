import React, { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useChanges, useSources } from '../api/hooks';
import type { SourceItem, SourceKind } from '../api/types';
import { Badge } from '../components/entity/Badge';
import { ErrorNotice, ListSkeleton } from '../components/entity/EntityStates';
import { PageFrame } from '../components/PageFrame';
import { SourceDocDrawer } from '../components/SourceDocDrawer';
import { formatLongDate } from '../utils/format';

const RECORD_KINDS: SourceKind[] = ['system', 'person', 'team', 'project'];
const FILTERS: { key: string; label: string; kinds: SourceKind[] | null }[] = [
  { key: 'all', label: 'All', kinds: null },
  { key: 'ticket', label: 'Tickets', kinds: ['ticket'] },
  { key: 'meeting', label: 'Meetings', kinds: ['meeting'] },
  { key: 'document', label: 'Documents', kinds: ['document'] },
  { key: 'record', label: 'Records', kinds: RECORD_KINDS },
];

const SHORT_KIND: Record<SourceKind, string> = {
  ticket: 'Ticket',
  meeting: 'Meeting',
  document: 'Document',
  person: 'Person',
  team: 'Team',
  project: 'Project',
  system: 'System',
};

function parseOpen(value: string | null): { kind: SourceKind; key: string } | null {
  if (!value) return null;
  const slash = value.indexOf('/');
  if (slash < 1) return null;
  const kind = value.slice(0, slash) as SourceKind;
  return SHORT_KIND[kind] ? { kind, key: value.slice(slash + 1) } : null;
}

const Stat: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex min-w-[96px] flex-col gap-0.5">
    <dt className="text-xs text-muted">{label}</dt>
    <dd className="m-0 text-lg font-semibold tabular-nums">{value}</dd>
  </div>
);

export const SourcesPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const sources = useSources();
  const changes = useChanges(20);
  const [filterText, setFilterText] = useState('');
  const filterKey = params.get('type') ?? 'all';
  const open = parseOpen(params.get('open'));

  const counts = sources.data?.counts ?? {};
  const records = RECORD_KINDS.reduce((n, k) => n + (counts[k] ?? 0), 0);
  const lastIngest = changes.data?.find((c) => c.kind === 'ingest');

  const items = useMemo(() => {
    const kinds = FILTERS.find((f) => f.key === filterKey)?.kinds ?? null;
    const needle = filterText.trim().toLowerCase();
    return (sources.data?.items ?? []).filter(
      (i) =>
        (!kinds || kinds.includes(i.kind)) &&
        (!needle || i.key.toLowerCase().includes(needle) || i.title.toLowerCase().includes(needle))
    );
  }, [sources.data, filterKey, filterText]);

  const setParam = (name: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: name === 'type' });
  };

  const header = (
    <>
      <h1 className="m-0 mr-2 text-sm font-medium text-text">Sources</h1>
      <div role="group" aria-label="Source type" className="flex flex-wrap items-center gap-1">
        {FILTERS.filter((f) => f.key !== 'document' || (counts.document ?? 0) > 0).map((f) => {
          const active = filterKey === f.key;
          return (
            <button
              key={f.key}
              type="button"
              aria-pressed={active}
              onClick={() => setParam('type', f.key === 'all' ? null : f.key)}
              className={`h-[26px] rounded-control border px-2.5 text-xs transition-colors ${
                active ? 'border-border bg-sidebar font-medium text-text' : 'border-transparent bg-transparent text-muted hover:bg-subtle'
              }`}
            >
              {f.label}
            </button>
          );
        })}
      </div>
    </>
  );

  return (
    <PageFrame header={header}>
      <div className="flex flex-col gap-4 px-5 pb-8 pt-5">
        <dl aria-label="Source counts" className="m-0 flex flex-wrap gap-x-8 gap-y-3">
          <Stat label="Tickets" value={counts.ticket ?? '–'} />
          <Stat label="Meeting notes" value={counts.meeting ?? '–'} />
          {(counts.document ?? 0) > 0 && <Stat label="Documents" value={counts.document} />}
          <Stat label="Records (company.db)" value={sources.data ? records : '–'} />
          <div className="flex min-w-[96px] flex-col gap-0.5">
            <dt className="text-xs text-muted">Last ingest</dt>
            <dd className="m-0 text-sm font-medium">
              {lastIngest ? (
                <span title={lastIngest.created_at}>
                  {formatLongDate(lastIngest.created_at) || lastIngest.created_at} · {lastIngest.title}
                </span>
              ) : changes.isLoading ? (
                '…'
              ) : (
                <span className="text-muted">No live ingest yet</span>
              )}
            </dd>
          </div>
        </dl>

        <div className="flex items-center gap-2">
          <label htmlFor="source-filter" className="sr-only">
            Filter sources
          </label>
          <input
            id="source-filter"
            type="search"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter by ID or title"
            className="h-[30px] w-full max-w-[320px] rounded-control border border-border bg-surface px-2.5 text-sm outline-none placeholder:text-muted focus:border-accent"
          />
          <span className="text-xs text-muted" aria-live="polite">
            {sources.data ? `${items.length} of ${sources.data.items.length}` : ''}
          </span>
        </div>

        {sources.isLoading && <ListSkeleton label="Loading sources" />}
        {sources.isError && <ErrorNotice title="Could not load sources" message={sources.error.message} onRetry={() => sources.refetch()} className="" />}
        {sources.data && items.length === 0 && <p className="m-0 py-6 text-muted">No sources match.</p>}

        {items.length > 0 && (
          <ul aria-label="Sources" className="m-0 list-none rounded-panel border border-divider p-0">
            {items.map((s) => (
              <SourceRow key={`${s.kind}/${s.key}`} item={s} onOpen={() => setParam('open', `${s.kind}/${s.key}`)} />
            ))}
          </ul>
        )}
      </div>
      <SourceDocDrawer open={open} onClose={() => setParam('open', null)} />
    </PageFrame>
  );
};

const SourceRow: React.FC<{ item: SourceItem; onOpen: () => void }> = ({ item, onOpen }) => (
  <li className="border-b border-row-divider last:border-b-0">
    <button
      type="button"
      onClick={onOpen}
      aria-haspopup="dialog"
      className="flex min-h-10 w-full flex-wrap items-center gap-x-3 gap-y-0.5 bg-transparent px-3 py-1.5 text-left transition-colors hover:bg-subtle"
    >
      <span className="w-16 shrink-0 text-xs text-muted">{SHORT_KIND[item.kind]}</span>
      {item.kind === 'ticket' && <span className="w-[72px] shrink-0 font-mono text-xs text-text-2">{item.key}</span>}
      <span className="min-w-0 flex-1 truncate font-medium" title={item.title}>
        {item.title}
      </span>
      {item.demo && <Badge tone="accent">Demo</Badge>}
      {item.kind === 'ticket' && item.detail && item.detail !== 'closed' && <Badge tone="stale">{item.detail}</Badge>}
      {item.kind !== 'ticket' && item.detail && (
        <span className="hidden max-w-[180px] truncate text-xs text-muted md:inline">{item.detail}</span>
      )}
      <span className="w-24 shrink-0 text-right text-xs text-muted max-sm:w-auto">
        {item.linked_decisions > 0
          ? `${item.linked_decisions} ${item.linked_decisions === 1 ? 'decision' : 'decisions'}`
          : '—'}
      </span>
      <span className="hidden w-24 shrink-0 text-right text-xs text-muted sm:inline">
        {item.date ? formatLongDate(item.date) || item.date : ''}
      </span>
    </button>
  </li>
);
