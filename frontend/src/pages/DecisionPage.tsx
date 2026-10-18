import React, { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from '../router';
import { useDecisionDetail } from '../api/hooks';
import type { DecisionDetail, DecisionRef, SourceRef } from '../api/types';
import { Avatar } from '../components/Avatar';
import { CytoscapeGraph } from '../components/CytoscapeGraph';
import { Badge, ChangedBadge, LeftBadge } from '../components/entity/Badge';
import { CypherBlock } from '../components/entity/CypherBlock';
import { DecisionTimeline } from '../components/entity/DecisionTimeline';
import { Section } from '../components/entity/Section';
import { PageFrame, Property, PropertyList, SidePanel } from '../components/PageFrame';
import { useLatestDiff } from '../components/ingest/ingestContext';
import { SourceDrawer } from '../components/SourceDrawer';
import { StatusIcon } from '../components/StatusIcon';
import { SystemChip } from '../components/SystemMark';
import { btnOutline, btnPrimary } from '../components/ui';
import { askHref, formatLongDate, questionAboutDecision } from '../utils/format';
import { isDecisionChanged } from '../utils/changes';
import { buildLineageGraph } from '../utils/lineage';
import { decisionHref, exploreHref, personHref, systemHref } from '../utils/links';
import { healthToStatus, STATUS_LABEL } from '../utils/model';

const DecisionLinks: React.FC<{ items: DecisionRef[] }> = ({ items }) =>
  items.length === 0 ? (
    <span className="text-muted">None</span>
  ) : (
    <span className="flex flex-wrap gap-x-2 gap-y-1">
      {items.map((d) => (
        <Link
          key={d.id}
          to={decisionHref(d.decision_code ?? d.id)}
          title={d.title}
          className="text-accent hover:underline"
        >
          {d.decision_code ?? d.title}
        </Link>
      ))}
    </span>
  );

const sourceTypeLabel = (type: string) =>
  type === 'ticket' ? 'Ticket' : type === 'meeting' ? 'Meeting notes' : 'Document';

const Skeleton: React.FC = () => (
  <div role="status" aria-label="Loading decision" className="flex flex-col gap-3 px-5 py-6 min-[900px]:px-8">
    <div className="skeleton h-4 w-20" />
    <div className="skeleton h-6 w-2/3" />
    <div className="skeleton h-4 w-1/2" />
    <div className="skeleton mt-3 h-72 w-full" />
  </div>
);

const LineageSection: React.FC<{ detail: DecisionDetail }> = ({ detail }) => {
  const navigate = useNavigate();
  const graph = useMemo(() => buildLineageGraph(detail), [detail]);
  const focusKey = `Decision:${detail.id}`;
  const [selected, setSelected] = useState<string | null>(focusKey);
  const hrefById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n.href])), [graph]);
  const chain =
    detail.lineage.supersedes.length +
    detail.lineage.superseded_by.length +
    detail.lineage.contradicts.length +
    detail.lineage.contradicted_by.length;

  return (
    <Section
      title="Lineage"
      meta={`${graph.nodes.length} nodes${graph.omitted ? `, ${graph.omitted} more hidden` : ''} · ${chain === 0 ? 'no related decisions' : `${chain} related decisions`}`}
    >
      <CytoscapeGraph
        elements={graph.elements}
        focusId={focusKey}
        layout="lr"
        className="h-[320px]"
        selectedId={selected}
        onSelect={(id) => {
          setSelected(id);
          const href = hrefById.get(id);
          if (href && id !== focusKey) navigate(href);
        }}
        fitSignal={0}
        ariaLabel={`Lineage of ${detail.decision_code}: ${graph.nodes.length} nodes. Sources feed in from the left; newer decisions are to the right.`}
      />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-divider px-3 py-2 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block w-5 border-t border-[#C9CCD3]" /> based on
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block w-5 border-t border-dashed border-[#9A9DA4]" /> superseded by
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block w-5 border-t border-dashed border-status-conflict" /> contradicts
        </span>
        <span className="ml-auto">Click a node to open it</span>
      </div>
      <ul aria-label="Lineage nodes" className="sr-only">
        {graph.nodes.map((n) => (
          <li key={n.id}>
            {n.href && !n.isFocus ? (
              <Link to={n.href}>
                {n.type}: {n.label}
              </Link>
            ) : (
              `${n.type}: ${n.label}${n.isFocus ? ' (this decision)' : ''}`
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
};

export const DecisionPage: React.FC = () => {
  const { code = '' } = useParams();
  const query = useDecisionDetail(code);
  const d = query.data;
  const latestDiff = useLatestDiff();
  const [openSource, setOpenSource] = useState<SourceRef | null>(null);

  const header = (
    <>
      <Link to="/decisions" className="hover:text-text">
        Decisions
      </Link>
      <span aria-hidden="true">/</span>
      <span className="font-medium text-text">{d?.decision_code ?? code}</span>
    </>
  );

  if (query.isLoading) {
    return (
      <PageFrame header={header}>
        <Skeleton />
      </PageFrame>
    );
  }
  if (query.isError || !d) {
    const notFound = query.error?.status === 404;
    return (
      <PageFrame header={header}>
        <div role={notFound ? 'status' : 'alert'} className="m-5 flex flex-col items-start gap-2 rounded-panel border border-divider bg-subtle p-4">
          <h1 className="m-0 text-lg font-semibold">{notFound ? 'Decision not found' : 'Could not load decision'}</h1>
          <p className="m-0 text-muted">
            {notFound ? `There is no decision ${code}. Decision codes look like DEC-11.` : query.error?.message}
          </p>
          <div className="flex flex-wrap gap-2">
            {!notFound && (
              <button type="button" className={btnOutline} onClick={() => query.refetch()}>
                Retry
              </button>
            )}
            <Link to="/decisions" className={btnOutline}>
              All decisions
            </Link>
          </div>
        </div>
      </PageFrame>
    );
  }

  const status = healthToStatus(d.health);
  const question = questionAboutDecision(d.title);
  const actions = (
    <>
      <Link to={exploreHref(d.id)} className={btnOutline}>
        Open in Explore
      </Link>
      <Link to={askHref(question)} className={btnOutline}>
        Ask about this
      </Link>
    </>
  );

  const panel = (
    <SidePanel label="Decision properties">
      <PropertyList>
        <Property label="Status">
          <StatusIcon status={status} size={13} />
          {STATUS_LABEL[status]}
        </Property>
        <Property label="Lifecycle">{d.status}</Property>
        <Property label="Decided by">
          <span className="flex flex-col gap-1">
            {d.deciders.length === 0 && <span className="text-muted">Unknown</span>}
            {d.deciders.map((p) => (
              <Link key={p.name} to={personHref(p.name)} className="hover:underline">
                {p.name}
                {p.departed && <span className="text-status-stale-text"> (left)</span>}
              </Link>
            ))}
          </span>
        </Property>
        <Property label="Date">{formatLongDate(d.decided_on) || 'Undated'}</Property>
        <Property label="Systems">
          <span className="flex flex-col gap-1">
            {d.system_names.map((s) => (
              <Link key={s} to={systemHref(s)} className="hover:underline">
                {s}
              </Link>
            ))}
          </span>
        </Property>
        <Property label="Supersedes">
          <DecisionLinks items={d.lineage.supersedes} />
        </Property>
        <Property label="Superseded by">
          <DecisionLinks items={d.lineage.superseded_by} />
        </Property>
        <Property label="Conflicts">
          <DecisionLinks items={[...d.lineage.contradicts, ...d.lineage.contradicted_by]} />
        </Property>
      </PropertyList>
      <div className="h-px bg-divider" />
      <CypherBlock trace={d.cypher} />
      <Link to={askHref(question)} className={`${btnPrimary} w-full`}>
        Ask about this
      </Link>
    </SidePanel>
  );

  return (
    <PageFrame header={header} actions={actions} panel={panel}>
      <div className="flex flex-col gap-6 px-5 py-6 min-[900px]:px-8">
        <header className="flex flex-col gap-2">
          <span className="flex items-center gap-2 text-muted">
            {d.decision_code}
            {isDecisionChanged(latestDiff, d.decision_code) && <ChangedBadge />}
          </span>
          <h1 className="m-0 text-[20px] font-semibold leading-tight">{d.title}</h1>
          <p className="m-0 flex items-start gap-2 text-text-2">
            <StatusIcon status={status} className="mt-[3px] shrink-0" />
            <span>
              <span className="font-medium">{STATUS_LABEL[status]}.</span> {d.health_reason}
            </span>
          </p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-text-2">
            {d.deciders.map((p) => (
              <Link key={p.name} to={personHref(p.name)} className="inline-flex items-center gap-1.5 hover:underline">
                <Avatar name={p.name} size={20} active={!p.departed} />
                {p.name}
                {p.departed && <LeftBadge leaveDate={p.leave_date} />}
              </Link>
            ))}
            {d.decided_on && <span className="text-muted">{formatLongDate(d.decided_on)}</span>}
            <span className="flex flex-wrap gap-1.5">
              {d.system_names.map((s) => (
                <Link key={s} to={systemHref(s)} className="rounded-chip hover:bg-subtle">
                  <SystemChip system={s} />
                </Link>
              ))}
            </span>
          </div>
        </header>

        <LineageSection detail={d} />

        <Section
          title="System timeline"
          meta={`${d.timeline.length} ${d.timeline.length === 1 ? 'decision' : 'decisions'} on ${d.system_names.join(', ') || 'no system'}`}
        >
          <DecisionTimeline items={d.timeline} currentId={d.id} />
        </Section>

        <Section title="Sources" meta={`${d.sources.length}`} id="sources">
          <div className="flex flex-col gap-2 p-3">
            {d.sources.length === 0 && <p className="m-0 text-muted">No sources recorded.</p>}
            {d.sources.map((s) => (
              <div key={s.id} className="flex flex-col gap-1 rounded-panel border border-divider px-3 py-2.5">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="font-medium">{s.id}</span>
                    <span className="text-muted">
                      {' '}
                      · {sourceTypeLabel(s.type)}
                      {s.date && ` · ${formatLongDate(s.date) || s.date}`}
                    </span>
                  </div>
                  {s.text && (
                    <button
                      type="button"
                      className={btnOutline}
                      aria-haspopup="dialog"
                      aria-label={`View source ${s.id}`}
                      onClick={() => setOpenSource(s)}
                    >
                      View source
                    </button>
                  )}
                </div>
                {s.title && s.title !== s.id && <div className="text-muted">{s.title}</div>}
                {s.quote && <blockquote className="m-0 text-text-2">“{s.quote}”</blockquote>}
              </div>
            ))}
            {d.evidence_quote && d.sources.length > 1 && (
              <div className="flex flex-col gap-1 rounded-panel bg-subtle px-3 py-2.5">
                <span className="text-xs text-muted">Evidence quote (recorded for the decision, not a single source)</span>
                <blockquote className="m-0 text-text-2">“{d.evidence_quote}”</blockquote>
              </div>
            )}
          </div>
        </Section>
        <SourceDrawer source={openSource} onClose={() => setOpenSource(null)} />

        <Section title="Impact" meta="Within two hops of its systems">
          <div className="flex flex-col gap-4 p-3">
            <div className="flex flex-col gap-1.5">
              <h3 className="m-0 text-xs font-medium text-muted">Teams</h3>
              <div className="flex flex-wrap gap-1.5">
                {d.impact.teams.length === 0 && <span className="text-muted">None</span>}
                {d.impact.teams.map((t) => (
                  <Badge key={t}>{t}</Badge>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <h3 className="m-0 text-xs font-medium text-muted">Projects</h3>
              <div className="flex flex-wrap gap-1.5">
                {d.impact.projects.length === 0 && <span className="text-muted">None</span>}
                {d.impact.projects.map((p) => (
                  <Badge key={p}>{p}</Badge>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <h3 className="m-0 text-xs font-medium text-muted">People</h3>
              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                {d.impact.people.map((p) => (
                  <li key={p.name}>
                    <Link to={personHref(p.name)} className="inline-flex items-center gap-2 hover:underline">
                      <Avatar name={p.name} size={18} active={!p.departed} />
                      {p.name}
                      {p.role && <span className="text-muted">· {p.role}</span>}
                      {p.departed && <LeftBadge leaveDate={p.leave_date} />}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Section>
      </div>
    </PageFrame>
  );
};
