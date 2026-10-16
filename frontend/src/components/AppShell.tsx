import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Layers, MessageCircle, Network, Search, Users } from 'lucide-react';
import { useDecisions, useGraph, usePeople, useSystems } from '../api/hooks';
import { useMediaQuery } from '../hooks/useMediaQuery';
import {
  buildDecisionRows,
  buildGraphIndex,
  countByStatus,
  type StatusKind,
} from '../utils/model';
import { CommandPalette } from './CommandPalette';
import { IngestProvider } from './ingest/IngestProvider';
import { StatusIcon } from './StatusIcon';

const NODE_TYPES = ['Decision', 'Person', 'System', 'Ticket', 'Meeting', 'Project', 'Team'];

const rowBase =
  'flex items-center gap-2 rounded-control px-2 text-text-2 transition-colors hover:bg-hover';

const NavItem: React.FC<{
  to: string;
  end?: boolean;
  icon: React.ReactNode;
  label: string;
  count?: number;
}> = ({ to, end, icon, label, count }) => (
  <NavLink
    to={to}
    end={end}
    className={({ isActive }) =>
      `${rowBase} h-[30px] shrink-0 ${isActive ? 'bg-hover font-medium text-text' : ''}`
    }
  >
    {({ isActive }) => (
      <>
        <span className={`inline-flex ${isActive ? 'text-accent' : ''}`}>{icon}</span>
        <span className="flex-1">{label}</span>
        {count !== undefined && (
          <span className={isActive ? 'text-text-2' : 'text-muted'}>{count}</span>
        )}
      </>
    )}
  </NavLink>
);

const GroupLabel: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="px-2 pb-1 text-xs font-medium text-muted">{children}</div>
);

const Views: React.FC<{
  counts: Record<StatusKind, number> | null;
  orphaned: number | null;
}> = ({ counts, orphaned }) => {
  const [params] = useSearchParams();
  const location = useLocation();
  const views = [
    { key: 'conflict', path: '/decisions', label: 'Conflicts', icon: <StatusIcon status="conflict" />, count: counts?.conflict },
    { key: 'superseded', path: '/decisions', label: 'Superseded', icon: <StatusIcon status="superseded" />, count: counts?.superseded },
    { key: 'orphaned', path: '/systems', label: 'Orphaned systems', icon: <StatusIcon status="stale" />, count: orphaned ?? undefined },
  ];
  return (
    <div className="flex flex-col gap-px">
      <GroupLabel>Views</GroupLabel>
      {views.map((v) => {
        const current = location.pathname === v.path && params.get('view') === v.key;
        return (
          <Link
            key={v.key}
            to={`${v.path}?view=${v.key}`}
            aria-current={current ? 'page' : undefined}
            className={`${rowBase} h-7 ${current ? 'bg-hover font-medium text-text' : ''}`}
          >
            {v.icon}
            <span className="flex-1">{v.label}</span>
            {v.count !== undefined && <span className={current ? 'text-text-2' : 'text-muted'}>{v.count}</span>}
          </Link>
        );
      })}
    </div>
  );
};

const GraphTypeFilters: React.FC<{ counts: Map<string, number> | null }> = ({ counts }) => {
  const [params, setParams] = useSearchParams();
  const hidden = new Set((params.get('hide') ?? '').split(',').filter(Boolean));
  const types = NODE_TYPES.filter((t) => (counts?.get(t) ?? 0) > 0);

  const toggle = (type: string) => {
    const next = new Set(hidden);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    const copy = new URLSearchParams(params);
    if (next.size > 0) copy.set('hide', [...next].join(','));
    else copy.delete('hide');
    setParams(copy, { replace: true });
  };

  return (
    <fieldset className="m-0 flex flex-col gap-1.5 border-0 px-2 py-0">
      <legend className="p-0 pb-1 text-xs font-medium text-muted">Show node types</legend>
      {types.map((type) => (
        <label key={type} className="flex min-h-[26px] cursor-pointer items-center gap-2 text-text-2">
          <input
            type="checkbox"
            checked={!hidden.has(type)}
            onChange={() => toggle(type)}
            className="m-0 h-3.5 w-3.5 accent-[#4F5BD5]"
          />
          {type}
          <span className="ml-auto text-muted">{counts?.get(type)}</span>
        </label>
      ))}
    </fieldset>
  );
};

export const AppShell: React.FC = () => {
  const location = useLocation();
  const isDesktop = useMediaQuery('(min-width: 900px)');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const paletteTrigger = useRef<HTMLElement | null>(null);

  const decisionsQuery = useDecisions();
  const graphQuery = useGraph();
  const index = useMemo(
    () => (graphQuery.data ? buildGraphIndex(graphQuery.data) : undefined),
    [graphQuery.data]
  );
  const rows = useMemo(
    () => (decisionsQuery.data ? buildDecisionRows(decisionsQuery.data, index) : []),
    [decisionsQuery.data, index]
  );
  const counts = decisionsQuery.data ? countByStatus(rows) : null;
  const systemsQuery = useSystems();
  const peopleQuery = usePeople();
  const orphaned = systemsQuery.data ? systemsQuery.data.filter((s) => s.orphaned).length : null;

  const openPalette = () => {
    paletteTrigger.current = document.activeElement as HTMLElement | null;
    setPaletteOpen(true);
  };
  const closePalette = () => {
    setPaletteOpen(false);
    paletteTrigger.current?.focus?.();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((open) => {
          if (!open) paletteTrigger.current = document.activeElement as HTMLElement | null;
          return !open;
        });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const onGraph = location.pathname === '/explore';
  const secondary = onGraph ? (
    <GraphTypeFilters counts={index?.countsByLabel ?? null} />
  ) : (
    <>
      <Views counts={counts} orphaned={orphaned} />
    </>
  );

  const footer = graphQuery.isError ? (
    <>
      <span className="h-1.5 w-1.5 rounded-full bg-status-conflict" aria-hidden="true" />
      Graph unavailable
    </>
  ) : (
    <>
      <span className="h-1.5 w-1.5 rounded-full bg-status-active" aria-hidden="true" />
      FalkorDB{graphQuery.data ? ` · ${graphQuery.data.total_nodes} nodes` : ''}
    </>
  );

  return (
    <IngestProvider>
      <div className="flex min-h-screen flex-col bg-bg text-text min-[900px]:flex-row">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-control focus:bg-accent focus:px-3 focus:py-2 focus:text-white"
        >
          Skip to content
        </a>

        <aside
          aria-label="Sidebar"
          className="box-border flex w-full shrink-0 flex-col gap-3 border-b border-border bg-sidebar px-2.5 py-3 min-[900px]:sticky min-[900px]:top-0 min-[900px]:h-screen min-[900px]:w-[232px] min-[900px]:gap-[18px] min-[900px]:overflow-y-auto min-[900px]:border-b-0 min-[900px]:border-r"
        >
          <div className="flex items-center gap-2 px-1.5 py-1">
            <span
              aria-hidden="true"
              className="flex h-5 w-5 items-center justify-center rounded-[5px] bg-accent text-[11px] font-semibold text-white"
            >
              DT
            </span>
            <span className="text-sm font-semibold">Decision Trace</span>
          </div>

          <button
            type="button"
            onClick={openPalette}
            className="flex h-[30px] items-center gap-2 rounded-control border border-border bg-surface px-2 text-left text-sm text-muted hover:bg-subtle"
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="flex-1">Search</span>
            <kbd className="rounded-[4px] border border-border px-1.5 py-px font-sans text-[11px]">⌘K</kbd>
          </button>

          <nav aria-label="Primary" className="flex gap-px overflow-x-auto min-[900px]:flex-col">
            <NavItem to="/" end icon={<MessageCircle size={15} aria-hidden="true" />} label="Ask" />
            <NavItem
              to="/decisions"
              icon={<CheckCircle2 size={15} aria-hidden="true" />}
              label="Decisions"
              count={decisionsQuery.data?.length}
            />
            <NavItem
              to="/systems"
              icon={<Layers size={15} aria-hidden="true" />}
              label="Systems"
              count={systemsQuery.data?.length}
            />
            <NavItem
              to="/people"
              icon={<Users size={15} aria-hidden="true" />}
              label="People"
              count={peopleQuery.data?.length}
            />
            <NavItem to="/explore" icon={<Network size={15} aria-hidden="true" />} label="Explore" />
          </nav>

          {isDesktop ? (
            <div className="flex flex-col gap-[18px]">{secondary}</div>
          ) : (
            <details className="group">
              <summary className="flex h-7 cursor-pointer items-center rounded-control px-2 text-sm text-text-2 hover:bg-hover">
                {onGraph ? 'Node types' : 'Views'}
              </summary>
              <div className="mt-2 flex flex-col gap-3">{secondary}</div>
            </details>
          )}

          <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted min-[900px]:mt-auto">
            {footer}
          </div>
        </aside>

        <Outlet />

        <CommandPalette
          open={paletteOpen}
          onClose={closePalette}
          decisions={rows}
          systems={systemsQuery.data ?? []}
          people={peopleQuery.data ?? []}
        />
      </div>
    </IngestProvider>
  );
};
