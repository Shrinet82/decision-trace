import React from 'react';
import { Link } from 'react-router-dom';
import { usePeople } from '../api/hooks';
import { Avatar } from '../components/Avatar';
import { LeftBadge } from '../components/entity/Badge';
import { ErrorNotice, ListSkeleton } from '../components/entity/EntityStates';
import { PageFrame } from '../components/PageFrame';
import { personHref } from '../utils/links';

export const PeoplePage: React.FC = () => {
  const query = usePeople();
  return (
    <PageFrame header={<h1 className="m-0 text-sm font-medium text-text">People</h1>}>
      {query.isLoading && <ListSkeleton label="Loading people" />}
      {query.isError && <ErrorNotice title="Could not load people" message={query.error.message} onRetry={() => query.refetch()} />}
      <ul className="m-0 list-none p-0">
        {(query.data ?? []).map((p) => (
          <li key={p.name}>
            <Link
              to={personHref(p.name)}
              className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 border-b border-row-divider px-5 py-2 transition-colors hover:bg-subtle"
            >
              <Avatar name={p.name} size={22} active={!p.departed} />
              <span className="min-w-[9rem] font-medium">{p.name}</span>
              {p.role && <span className="hidden text-muted sm:inline">{p.role}</span>}
              {p.departed && <LeftBadge leaveDate={p.leave_date} />}
              <span className="ml-auto flex items-center gap-3 text-muted">
                <span className="hidden md:inline">{p.teams.join(', ')}</span>
                {p.systems_owned.length > 0 && (
                  <span className="hidden sm:inline">owns {p.systems_owned.join(', ')}</span>
                )}
                <span className="w-24 text-right">
                  {p.decision_count} {p.decision_count === 1 ? 'decision' : 'decisions'}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </PageFrame>
  );
};
