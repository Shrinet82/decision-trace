import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Database, MessageCircle, Network, Search } from 'lucide-react';
import { useDecisions, useGraph } from '../api/hooks';
import { useMediaQuery } from '../hooks/useMediaQuery';
import {
  buildDecisionRows,
  buildGraphIndex,
  countByStatus,
  STATUS_LABEL,
  systemsWithDecisions,
  type StatusKind,
} from '../utils/model';
import { CommandPalette } from './CommandPalette';
import { StatusIcon } from './StatusIcon';
import { SystemSquare } from './SystemMark';

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

const Views: React.FC<{ counts: Record<StatusKind, number> | null }> = ({ counts }) => {
  const [params] = useSearchParams();
  const location = useLocation();
  const current = location.pathname === '/decisions' ? params.get('view') : null;
  const views: { key: StatusKind; param: string }[] = [
    { key: 'conflict', param: 'conflict' },
    { key: 'stale', param: 'stale' },
    { key: 'superseded', param: 'superseded' },
  ];
  return (
    <div className="flex flex-col gap-px">
      <GroupLabel>Views</GroupLabel>
      {views.map(({ key, param }) => (
        <Link
          key={key}
          to={`/decisions?view=${param}`}
          aria-current={current === param ? 'page' : undefined}
          className={`${rowBase} h-7 ${current === param ? 'bg-hover font-medium text-text' : ''}`}
        >
          <StatusIcon status={key} />
          <span className="flex-1">{key === 'conflict' ? 'Conflicts' : STATUS_LABEL[key]}</span>
          {counts && (
            <span className={current === param ? 'text-text-2' : 'text-muted'}>{counts[key]}</span>
          )}
        </Link>
      ))}
    </div>
  );
};

const Systems: React.FC<{ systems: { name: string; decisionCount: number }[] }> = ({ systems }) => {
  const [params] = useSearchParams();
  const location = useLocation();
  const current = location.pathname === '/decisions' ? params.get('system') : null;
  if (systems.length === 0) return null;
  return (
    <div className="flex flex-col gap-px">
      <GroupLabel>Systems</GroupLabel>
      {systems.map((s) => (
        <Link
          key={s.name}
          to={`/decisions?system=${encodeURIComponent(s.name)}`}
          aria-current={current === s.name ? 'page' : undefined}
          className={`${rowBase} h-7 ${current === s.name ? 'bg-hover font-medium text-text' : ''}`}
        >
          <SystemSquare system={s.name} />
          <span className="min-w-0 flex-1 truncate">{s.name}</span>
          <span className={current === s.name ? 'text-text-2' : 'text-muted'}>{s.decisionCount}</span>
        </Link>
      ))}
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
  const systems = useMemo(() => (index ? systemsWithDecisions(index) : []), [index]);

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

  const onGraph = location.pathname === '/graph';
  const secondary = onGraph ? (
    <GraphTypeFilters counts={index?.countsByLabel ?? null} />
  ) : (
    <>
      <Views counts={counts} />
      <Systems systems={systems} />
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
          <NavItem to="/graph" icon={<Network size={15} aria-hidden="true" />} label="Graph" />
          <NavItem to="/sources" icon={<Database size={15} aria-hidden="true" />} label="Sources" />
        </nav>

        {isDesktop ? (
          <div className="flex flex-col gap-[18px]">{secondary}</div>
        ) : (
          <details className="group">
            <summary className="flex h-7 cursor-pointer items-center rounded-control px-2 text-sm text-text-2 hover:bg-hover">
              {onGraph ? 'Node types' : 'Views and systems'}
            </summary>
            <div className="mt-2 flex flex-col gap-3">{secondary}</div>
          </details>
        )}

        <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted min-[900px]:mt-auto">
          {footer}
        </div>
      </aside>

      <Outlet />

      <CommandPalette open={paletteOpen} onClose={closePalette} decisions={rows} />
    </div>
  );
};
