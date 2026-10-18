import React from 'react';
import { Link, useSearchParams } from '../router';
import { useSystems } from '../api/hooks';
import { Avatar } from '../components/Avatar';
import { Badge, LeftBadge } from '../components/entity/Badge';
import { ErrorNotice, ListSkeleton } from '../components/entity/EntityStates';
import { PageFrame } from '../components/PageFrame';
import { SystemSquare } from '../components/SystemMark';
import { systemHref } from '../utils/links';

export const SystemsPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const query = useSystems();
  const orphanedOnly = params.get('view') === 'orphaned';
  const items = (query.data ?? []).filter((s) => !orphanedOnly || s.orphaned);

  const header = (
    <>
      <h1 className="m-0 mr-2 text-sm font-medium text-text">Systems</h1>
      <div role="group" aria-label="System filter" className="flex items-center gap-1">
        {[
          { key: null, label: 'All' },
          { key: 'orphaned', label: 'Orphaned' },
        ].map((t) => {
          const active = (params.get('view') ?? null) === t.key;
          return (
            <button
              key={t.label}
              type="button"
              aria-pressed={active}
              onClick={() => setParams(t.key ? { view: t.key } : {}, { replace: true })}
              className={`h-[26px] rounded-control border px-2.5 text-xs transition-colors ${
                active ? 'border-border bg-sidebar font-medium text-text' : 'border-transparent bg-transparent text-muted hover:bg-subtle'
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
    </>
  );

  return (
    <PageFrame header={header}>
      {query.isLoading && <ListSkeleton label="Loading systems" />}
      {query.isError && <ErrorNotice title="Could not load systems" message={query.error.message} onRetry={() => query.refetch()} />}
      {query.data && items.length === 0 && <p className="m-0 px-5 py-8 text-muted">No systems match.</p>}
      <ul className="m-0 list-none p-0">
        {items.map((s) => (
          <li key={s.name}>
            <Link
              to={systemHref(s.name)}
              className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 border-b border-row-divider px-5 py-2 transition-colors hover:bg-subtle"
            >
              <SystemSquare system={s.name} />
              <span className="min-w-[8rem] font-medium">{s.name}</span>
              {s.system_type && <span className="hidden text-muted sm:inline">{s.system_type}</span>}
              {s.orphaned && <Badge tone="stale">Orphaned</Badge>}
              <span className="ml-auto flex items-center gap-3 text-muted">
                {s.owner && (
                  <span className="inline-flex items-center gap-1.5">
                    <Avatar name={s.owner.name} size={20} active={!s.owner.departed} />
                    <span className="hidden text-text-2 md:inline">{s.owner.name}</span>
                    {s.owner.departed && <LeftBadge leaveDate={s.owner.leave_date} />}
                  </span>
                )}
                <span className="w-24 text-right">
                  {s.decision_count} {s.decision_count === 1 ? 'decision' : 'decisions'}
                </span>
                <span className="hidden w-20 text-right sm:inline">{s.ticket_count} tickets</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </PageFrame>
  );
};
