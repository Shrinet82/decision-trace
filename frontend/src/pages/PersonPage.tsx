import React from 'react';
import { Link, useParams } from 'react-router-dom';
import { usePerson } from '../api/hooks';
import { Avatar } from '../components/Avatar';
import { Badge, LeftBadge } from '../components/entity/Badge';
import { CypherBlock } from '../components/entity/CypherBlock';
import { DecisionTimeline } from '../components/entity/DecisionTimeline';
import { DetailSkeleton, LoadError } from '../components/entity/EntityStates';
import { Section } from '../components/entity/Section';
import { PageFrame, Property, PropertyList, SidePanel } from '../components/PageFrame';
import { SystemSquare } from '../components/SystemMark';
import { btnPrimary } from '../components/ui';
import { askHref, formatLongDate } from '../utils/format';
import { systemHref } from '../utils/links';

export const PersonPage: React.FC = () => {
  const { name = '' } = useParams();
  const query = usePerson(name);
  const p = query.data;

  const header = (
    <>
      <Link to="/people" className="hover:text-text">
        People
      </Link>
      <span aria-hidden="true">/</span>
      <span className="font-medium text-text">{p?.name ?? name}</span>
    </>
  );

  if (query.isLoading) return <PageFrame header={header}><DetailSkeleton label="Loading person" /></PageFrame>;
  if (query.isError || !p) {
    return (
      <PageFrame header={header}>
        <LoadError notFound={query.error?.status === 404} what="Person" message={query.error?.message} backTo="/people" backLabel="All people" />
      </PageFrame>
    );
  }

  const question = `What decisions did ${p.name} make?`;
  const panel = (
    <SidePanel label="Person properties">
      <PropertyList>
        {p.role && <Property label="Role">{p.role}</Property>}
        <Property label="Status">{p.departed ? <LeftBadge leaveDate={p.leave_date} /> : 'Active'}</Property>
        {p.start_date && <Property label="Joined">{formatLongDate(p.start_date)}</Property>}
        {p.departed && p.leave_date && <Property label="Left">{formatLongDate(p.leave_date)}</Property>}
        <Property label="Decisions">{p.decision_count}</Property>
        <Property label="Tickets">
          {p.tickets_raised} raised · {p.tickets_assigned} assigned
        </Property>
        <Property label="Meetings">{p.meetings_attended}</Property>
      </PropertyList>
      <div className="h-px bg-divider" />
      <CypherBlock trace={p.cypher} />
      <Link to={askHref(question)} className={`${btnPrimary} w-full`}>
        Ask about this
      </Link>
    </SidePanel>
  );

  return (
    <PageFrame header={header} panel={panel}>
      <div className="flex flex-col gap-6 px-5 py-6 min-[900px]:px-8">
        <header className="flex flex-wrap items-center gap-3">
          <Avatar name={p.name} size={40} active={!p.departed} />
          <div className="flex min-w-0 flex-col">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="m-0 text-[20px] font-semibold">{p.name}</h1>
              {p.departed && <LeftBadge leaveDate={p.leave_date} />}
            </div>
            <span className="text-muted">{[p.role, ...p.teams].filter(Boolean).join(' · ')}</span>
          </div>
        </header>

        <Section title="Decisions made" meta={`${p.decisions.length}, oldest first`}>
          <DecisionTimeline items={p.decisions} showDeciders={false} emptyText={`${p.name} has no recorded decisions.`} />
        </Section>

        <Section title="Systems owned" meta={`${p.owned.length}`}>
          <ul className="m-0 list-none p-0">
            {p.owned.length === 0 && <li className="px-3 py-4 text-muted">None</li>}
            {p.owned.map((s) => (
              <li key={s.name}>
                <Link to={systemHref(s.name)} className="flex items-center gap-2 border-b border-row-divider px-3 py-2 last:border-b-0 hover:bg-subtle">
                  <SystemSquare system={s.name} />
                  <span className="font-medium">{s.name}</span>
                  {s.orphaned && <Badge tone="stale">Orphaned</Badge>}
                </Link>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Teams and projects">
          <div className="flex flex-col gap-3 p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-20 text-xs text-muted">Member of</span>
              {p.teams.length === 0 && <span className="text-muted">None</span>}
              {p.teams.map((t) => <Badge key={t}>{t}</Badge>)}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-20 text-xs text-muted">Leads</span>
              {p.teams_led.length + p.projects_led.length === 0 && <span className="text-muted">None</span>}
              {[...p.teams_led, ...p.projects_led].map((t) => <Badge key={t}>{t}</Badge>)}
            </div>
          </div>
        </Section>
      </div>
    </PageFrame>
  );
};
