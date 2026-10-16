import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { LayoutGrid, SlidersHorizontal, X } from 'lucide-react';
import { useDecisionDetail, useDecisions, useGraph } from '../api/hooks';
import { Avatar } from '../components/Avatar';
import { PageFrame, Property, PropertyList, SidePanel } from '../components/PageFrame';
import { PopoverButton } from '../components/Popover';
import { StatusIcon } from '../components/StatusIcon';
import { SystemChip, SystemSquare } from '../components/SystemMark';
import { btnOutline, btnSecondary } from '../components/ui';
import { askHref, formatLongDate, formatShortDate, questionAboutDecision } from '../utils/format';
import {
  buildDecisionRows,
  buildGraphIndex,
  isPersonActive,
  STATUS_LABEL,
  STATUS_ORDER,
  type DecisionRow,
  type GraphIndex,
  type StatusKind,
} from '../utils/model';
import { useMediaQuery } from '../hooks/useMediaQuery';

type Tab = 'all' | 'review' | 'active';
type GroupBy = 'status' | 'system';

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'review', label: 'Needs review' },
  { key: 'active', label: 'Active' },
];

const COLLAPSED_ROWS = 5;
const COLLAPSE_THRESHOLD = 6;

interface Group {
  key: string;
  label: string;
  icon: React.ReactNode;
  rows: DecisionRow[];
}

function personIsActive(index: GraphIndex | undefined, name: string | null): boolean {
  if (!index || !name) return true;
  const node = index.find(name.split(',')[0].trim());
  return node ? isPersonActive(node) : true;
}

function sortRows(rows: DecisionRow[]): DecisionRow[] {
  return [...rows].sort(
    (a, b) => (b.decidedOn ?? '').localeCompare(a.decidedOn ?? '') || a.title.localeCompare(b.title)
  );
}

const SkeletonRows: React.FC = () => (
  <div role="status" aria-label="Loading decisions" className="flex flex-col">
    {Array.from({ length: 8 }).map((_, i) => (
      <div key={i} className="flex h-10 items-center gap-3 border-b border-row-divider px-5">
        <div className="skeleton h-3 w-14" />
        <div className="skeleton h-3.5 w-3.5 rounded-full" />
        <div className="skeleton h-3 flex-1" />
        <div className="skeleton h-5 w-24 rounded-chip" />
      </div>
    ))}
  </div>
);

const DecisionRowButton: React.FC<{
  row: DecisionRow;
  selected: boolean;
  index: GraphIndex | undefined;
  onSelect: () => void;
}> = ({ row, selected, index, onSelect }) => (
  <li>
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={`flex h-10 w-full items-center gap-3 border-0 border-b border-row-divider px-5 text-left transition-colors hover:bg-subtle ${
        selected ? 'bg-selected hover:bg-selected' : 'bg-transparent'
      }`}
    >
      <span className="hidden w-[68px] shrink-0 whitespace-nowrap text-muted sm:inline">{row.ticketId ?? ''}</span>
      <StatusIcon status={row.status} />
      <span
        className={`min-w-0 flex-1 truncate ${row.status === 'superseded' ? 'text-muted' : 'font-medium'}`}
      >
        {row.title}
      </span>
      {row.hint && (
        <span
          className={`hidden shrink-0 text-xs md:inline ${
            row.hint.tone === 'stale' ? 'text-status-stale-text' : 'text-muted'
          }`}
        >
          {row.hint.text}
        </span>
      )}
      {row.system && <SystemChip system={row.system} className="hidden sm:inline-flex" />}
      {row.decidedBy && (
        <Avatar name={row.decidedBy} size={22} active={personIsActive(index, row.decidedBy)} />
      )}
      <span className="hidden w-14 shrink-0 text-right text-muted sm:inline">
        {formatShortDate(row.decidedOn)}
      </span>
    </button>
  </li>
);

const Callout: React.FC<{ row: DecisionRow; otherTitle?: string }> = ({ row, otherTitle }) => {
  if (row.status === 'active') return null;
  const isConflict = row.status === 'conflict';
  const title =
    row.status === 'conflict'
      ? `Conflicts with ${otherTitle ?? 'another decision'}`
      : row.status === 'superseded'
        ? `Superseded${otherTitle ? ` by ${otherTitle}` : ''}`
        : 'Possibly stale';
  return (
    <div
      className={`flex flex-col gap-1 rounded-panel border px-3 py-2.5 ${
        isConflict
          ? 'border-status-conflict-border bg-status-conflict-bg'
          : 'border-divider bg-subtle'
      }`}
    >
      <div
        className={`font-medium ${
          isConflict
            ? 'text-status-conflict-text'
            : row.status === 'stale'
              ? 'text-status-stale-text'
              : 'text-text-2'
        }`}
      >
        {title}
      </div>
      <div className="text-text-2">{row.healthReason}</div>
    </div>
  );
};

const Peek: React.FC<{ row: DecisionRow | undefined; index: GraphIndex | undefined }> = ({
  row,
  index,
}) => {
  const detail = useDecisionDetail(row?.id);
  if (!row) {
    return (
      <SidePanel label="Selected decision">
        <p className="m-0 text-muted">Select a decision to see its details.</p>
      </SidePanel>
    );
  }
  const d = detail.data;
  const other = row.status === 'conflict' ? d?.contradicts[0] : d?.superseded_by[0];
  const sources = d?.sources.map((s) => (s.type === 'ticket' ? s.id : (s.title ?? s.id))) ?? [];
  const question =
    row.status === 'conflict' && other
      ? `Which applies: "${row.title}" or "${other}"?`
      : questionAboutDecision(row.title);

  return (
    <SidePanel label="Selected decision" className="min-[900px]:max-w-[320px]" >
      <div className="flex items-center justify-between">
        <span className="text-muted">{row.ticketId ?? 'Decision'}</span>
        <Link to={askHref(questionAboutDecision(row.title))} className="font-medium text-accent hover:underline">
          Open
        </Link>
      </div>
      <h2 className="m-0 text-xl font-semibold">{row.title}</h2>
      <Callout row={row} otherTitle={other} />
      <PropertyList labelWidth={90}>
        {row.decidedBy && (
          <Property label="Decided by">
            <Avatar name={row.decidedBy} size={18} active={personIsActive(index, row.decidedBy)} />
            {row.decidedBy}
          </Property>
        )}
        {row.decidedOn && <Property label="Date">{formatLongDate(row.decidedOn) || row.decidedOn}</Property>}
        {row.system && (
          <Property label="System">
            <SystemSquare system={row.system} />
            {row.system}
          </Property>
        )}
        {detail.isLoading ? (
          <Property label="Based on">
            <span className="skeleton h-3.5 w-24" />
          </Property>
        ) : (
          sources.length > 0 && <Property label="Based on">{sources.join(', ')}</Property>
        )}
      </PropertyList>
      <Link to={askHref(question)} className={btnSecondary}>
        {row.status === 'conflict' ? 'Ask which one applies' : 'Ask about this'}
      </Link>
    </SidePanel>
  );
};

export const DecisionsPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const isDesktop = useMediaQuery('(min-width: 900px)');
  const decisionsQuery = useDecisions();
  const graphQuery = useGraph();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const index = useMemo(
    () => (graphQuery.data ? buildGraphIndex(graphQuery.data) : undefined),
    [graphQuery.data]
  );
  const allRows = useMemo(
    () => (decisionsQuery.data ? buildDecisionRows(decisionsQuery.data, index) : []),
    [decisionsQuery.data, index]
  );

  const tab = (params.get('tab') as Tab) || 'all';
  const view = params.get('view') as StatusKind | null;
  const system = params.get('system');
  const groupBy: GroupBy = params.get('group') === 'system' ? 'system' : 'status';
  const selectedParam = params.get('selected');

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const systemOptions = useMemo(
    () => [...new Set(allRows.map((r) => r.system).filter((s): s is string => Boolean(s)))].sort(),
    [allRows]
  );

  const rows = useMemo(
    () =>
      allRows.filter((r) => {
        if (tab === 'review' && r.status !== 'conflict' && r.status !== 'stale') return false;
        if (tab === 'active' && r.status !== 'active') return false;
        if (view && r.status !== view) return false;
        if (system && r.system !== system) return false;
        return true;
      }),
    [allRows, tab, view, system]
  );

  const groups = useMemo<Group[]>(() => {
    if (groupBy === 'system') {
      const names = [...new Set(rows.map((r) => r.system ?? 'No system'))].sort();
      return names.map((name) => ({
        key: `system:${name}`,
        label: name,
        icon: <SystemSquare system={name === 'No system' ? null : name} />,
        rows: sortRows(rows.filter((r) => (r.system ?? 'No system') === name)),
      }));
    }
    return STATUS_ORDER.map((status) => ({
      key: `status:${status}`,
      label: STATUS_LABEL[status],
      icon: <StatusIcon status={status} />,
      rows: sortRows(rows.filter((r) => r.status === status)),
    })).filter((g) => g.rows.length > 0);
  }, [rows, groupBy]);

  const firstRow = groups[0]?.rows[0];
  const selectedRow =
    rows.find((r) => r.id === selectedParam) ?? firstRow;

  useEffect(() => {
    setExpanded(new Set());
  }, [tab, view, system, groupBy]);

  const select = (row: DecisionRow) => {
    setParam('selected', row.id);
    if (!isDesktop) {
      requestAnimationFrame(() =>
        document.querySelector('[aria-label="Selected decision"]')?.scrollIntoView?.({ behavior: 'smooth' })
      );
    }
  };

  const header = (
    <>
      <h1 className="m-0 mr-2 text-sm font-medium text-text">Decisions</h1>
      <div role="group" aria-label="Decision filter" className="flex items-center gap-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-pressed={tab === t.key}
            onClick={() => setParam('tab', t.key === 'all' ? null : t.key)}
            className={`h-[26px] rounded-control border px-2.5 text-xs transition-colors ${
              tab === t.key
                ? 'border-border bg-sidebar font-medium text-text'
                : 'border-transparent bg-transparent text-muted hover:bg-subtle'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </>
  );

  const selectClass =
    'h-7 w-full rounded-control border border-border bg-surface px-2 text-xs text-text-2';

  const actions = (
    <>
      <PopoverButton label="Filter" icon={<SlidersHorizontal className="h-3 w-3" aria-hidden="true" />}>
        <label className="flex flex-col gap-1 text-xs text-muted">
          System
          <select
            className={selectClass}
            value={system ?? ''}
            onChange={(e) => setParam('system', e.target.value || null)}
          >
            <option value="">All systems</option>
            {systemOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Status
          <select
            className={selectClass}
            value={view ?? ''}
            onChange={(e) => setParam('view', e.target.value || null)}
          >
            <option value="">Any status</option>
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
      </PopoverButton>
      <PopoverButton label="Display" icon={<LayoutGrid className="h-3 w-3" aria-hidden="true" />}>
        <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
          <legend className="p-0 pb-1 text-xs text-muted">Group by</legend>
          {(['status', 'system'] as GroupBy[]).map((g) => (
            <label key={g} className="flex items-center gap-2 text-text-2">
              <input
                type="radio"
                name="group-by"
                checked={groupBy === g}
                onChange={() => setParam('group', g === 'status' ? null : g)}
                className="m-0 accent-[#4F5BD5]"
              />
              {g === 'status' ? 'Status' : 'System'}
            </label>
          ))}
        </fieldset>
      </PopoverButton>
    </>
  );

  const activeFilters = [
    view && { key: 'view', label: `Status: ${STATUS_LABEL[view] ?? view}` },
    system && { key: 'system', label: `System: ${system}` },
  ].filter(Boolean) as { key: string; label: string }[];

  return (
    <PageFrame header={header} actions={actions} panel={<Peek row={selectedRow} index={index} />}>
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-row-divider px-5 py-2">
          {activeFilters.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setParam(f.key, null)}
              aria-label={`Remove filter ${f.label}`}
              className="inline-flex h-[22px] items-center gap-1.5 rounded-chip border border-border px-2 text-xs text-text-2 hover:bg-subtle"
            >
              {f.label}
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}

      {decisionsQuery.isLoading && <SkeletonRows />}

      {decisionsQuery.isError && (
        <div role="alert" className="m-5 flex flex-col items-start gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg p-3">
          <span className="font-medium text-status-conflict-text">Could not load decisions</span>
          <span className="text-text-2">{decisionsQuery.error?.message}</span>
          <button type="button" className={btnOutline} onClick={() => decisionsQuery.refetch()}>
            Retry
          </button>
        </div>
      )}

      {decisionsQuery.data && groups.length === 0 && (
        <p className="m-0 px-5 py-8 text-muted">No decisions match these filters.</p>
      )}

      {groups.map((group) => {
        const isExpanded = expanded.has(group.key);
        const collapsible = group.rows.length > COLLAPSE_THRESHOLD;
        const visible = collapsible && !isExpanded ? group.rows.slice(0, COLLAPSED_ROWS) : group.rows;
        return (
          <section key={group.key} aria-label={`${group.label}, ${group.rows.length}`}>
            <h2 className="m-0 flex h-9 items-center gap-2 border-b border-divider bg-subtle px-5 text-sm font-medium">
              {group.icon}
              {group.label}
              <span className="font-normal text-muted">{group.rows.length}</span>
            </h2>
            <ul className="m-0 list-none p-0">
              {visible.map((row) => (
                <DecisionRowButton
                  key={row.id}
                  row={row}
                  index={index}
                  selected={selectedRow?.id === row.id}
                  onSelect={() => select(row)}
                />
              ))}
            </ul>
            {collapsible && !isExpanded && (
              <button
                type="button"
                onClick={() => setExpanded((prev) => new Set(prev).add(group.key))}
                className="flex h-9 w-full items-center border-0 border-b border-row-divider bg-transparent px-5 text-left text-muted hover:bg-subtle min-[900px]:pl-[104px]"
              >
                Show {group.rows.length - COLLAPSED_ROWS} more
              </button>
            )}
          </section>
        );
      })}
    </PageFrame>
  );
};
