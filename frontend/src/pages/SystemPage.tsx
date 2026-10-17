import React from 'react';
import { Link, useParams } from 'react-router-dom';
import { useSystem } from '../api/hooks';
import { Avatar } from '../components/Avatar';
import { Badge, ChangedBadge, LeftBadge } from '../components/entity/Badge';
import { CypherBlock } from '../components/entity/CypherBlock';
import { DecisionTimeline } from '../components/entity/DecisionTimeline';
import { DetailSkeleton, LoadError } from '../components/entity/EntityStates';
import { Section } from '../components/entity/Section';
import { PageFrame, Property, PropertyList, SidePanel } from '../components/PageFrame';
import { useLatestDiff } from '../components/ingest/ingestContext';
import { SystemSquare } from '../components/SystemMark';
import { btnPrimary } from '../components/ui';
import { isSystemChanged } from '../utils/changes';
import { askHref, formatLongDate } from '../utils/format';
import { personHref } from '../utils/links';

const ROLE_LABEL: Record<string, string> = { owner: 'Owner', decider: 'Decider', tickets: 'Tickets' };

export const SystemPage: React.FC = () => {
  const { name = '' } = useParams();
  const query = useSystem(name);
  const s = query.data;
  const latestDiff = useLatestDiff();

  const header = (
    <>
      <Link to="/systems" className="hover:text-text">
        Systems
      </Link>
      <span aria-hidden="true">/</span>
      <span className="font-medium text-text">{s?.name ?? name}</span>
    </>
  );

  if (query.isLoading) return <PageFrame header={header}><DetailSkeleton label="Loading system" /></PageFrame>;
  if (query.isError || !s) {
    return (
      <PageFrame header={header}>
        <LoadError notFound={query.error?.status === 404} what="System" message={query.error?.status === 404 ? `There is no system named "${name}".` : query.error?.message} backTo="/systems" backLabel="All systems" onRetry={() => query.refetch()} />
      </PageFrame>
    );
  }

  const question = `Who owns ${s.name} and which decisions affect it?`;
  const panel = (
    <SidePanel label="System properties">
      <PropertyList>
        <Property label="Owner">
          {s.owner ? (
            <Link to={personHref(s.owner.name)} className="hover:underline">
              {s.owner.name}
              {s.owner.departed && <span className="text-status-stale-text"> (left)</span>}
            </Link>
          ) : (
            <span className="text-muted">None</span>
          )}
        </Property>
        <Property label="Ownership">{s.orphaned ? <Badge tone="stale">Orphaned</Badge> : 'Active owner'}</Property>
        {s.system_type && <Property label="Type">{s.system_type}</Property>}
        {s.vendor && <Property label="Vendor">{s.vendor}</Property>}
        <Property label="Decisions">{s.decision_count}</Property>
        <Property label="Tickets">{s.ticket_count}</Property>
        <Property label="Teams">{s.teams.join(', ') || <span className="text-muted">None</span>}</Property>
      </PropertyList>
      <div className="h-px bg-divider" />
      <CypherBlock trace={s.cypher} />
      <Link to={askHref(question)} className={`${btnPrimary} w-full`}>
        Ask about this
      </Link>
    </SidePanel>
  );

  return (
    <PageFrame header={header} panel={panel}>
      <div className="flex flex-col gap-6 px-5 py-6 min-[900px]:px-8">
        <header className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <SystemSquare system={s.name} size={10} />
            <h1 className="m-0 text-[20px] font-semibold">{s.name}</h1>
            {s.orphaned && <Badge tone="stale">Orphaned</Badge>}
            {isSystemChanged(latestDiff, s.name) && <ChangedBadge />}
          </div>
          <p className="m-0 text-muted">{[s.system_type, s.vendor].filter(Boolean).join(' · ')}</p>
          {s.orphaned && s.owner && (
            <div className="flex flex-col gap-1 rounded-panel border border-[#EBD3A6] bg-[#FDF8EE] px-3 py-2.5">
              <span className="font-medium text-status-stale-text">No active owner</span>
              <span className="text-text-2">
                {s.owner.name} owns this system but left the company
                {s.owner.leave_date ? ` on ${formatLongDate(s.owner.leave_date)}` : ''}. No successor is recorded.
              </span>
            </div>
          )}
        </header>

        <Section title="Decisions" meta={`${s.decisions.length}, oldest first`}>
          <DecisionTimeline items={s.decisions} emptyText="No decision is recorded for this system." />
        </Section>

        <Section title="People involved" meta={`${s.people.length}`}>
          <ul className="m-0 list-none p-0">
            {s.people.map((p) => (
              <li key={p.name}>
                <Link to={personHref(p.name)} className="flex flex-wrap items-center gap-2 border-b border-row-divider px-3 py-2 last:border-b-0 hover:bg-subtle">
                  <Avatar name={p.name} size={20} active={!p.departed} />
                  <span className="font-medium">{p.name}</span>
                  {p.role && <span className="text-muted">{p.role}</span>}
                  {p.departed && <LeftBadge leaveDate={p.leave_date} />}
                  <span className="ml-auto flex flex-wrap gap-1.5">
                    {p.roles.map((r) => (
                      <Badge key={r}>{r === 'tickets' ? `${p.ticket_count} tickets` : ROLE_LABEL[r] ?? r}</Badge>
                    ))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </PageFrame>
  );
};
