import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from '../router';
import { useDecisions, useGraph } from '../api/hooks';
import type { GraphNode } from '../api/types';
import { Avatar } from '../components/Avatar';
import { CompanyMap } from '../components/CompanyMap';
import { CytoscapeGraph } from '../components/CytoscapeGraph';
import { PageFrame, Property, PropertyList, SidePanel } from '../components/PageFrame';
import { StatusIcon } from '../components/StatusIcon';
import { btnOutline, btnPrimary } from '../components/ui';
import { hiddenTypesFromParams, searchNodes, TYPE_COLOR, toMapElements } from '../utils/companyMap';
import { askHref, formatLongDate, questionAboutDecision } from '../utils/format';
import { decisionHref, personHref, systemHref } from '../utils/links';
import {
  buildCypher,
  neighborhood,
  toCytoscapeElements,
  type Hops,
} from '../utils/graphConverter';
import {
  buildGraphIndex,
  decisionCode,
  healthToStatus,
  isPersonActive,
  nodeTitle,
  STATUS_LABEL,
  type GraphIndex,
  type StatusKind,
} from '../utils/model';

const NEXT_HOPS: Record<string, Hops> = { '1': 2, '2': 3, '3': 'all' };

function hopsLabel(hops: Hops): string {
  return hops === 'all' ? 'full graph' : `${hops} ${hops === 1 ? 'hop' : 'hops'}`;
}

function askAbout(node: GraphNode): string {
  const name = nodeTitle(node);
  const p = node.properties ?? {};
  switch (node.label) {
    case 'Decision':
      return questionAboutDecision(name);
    case 'Person':
      return `What decisions did ${name} make?`;
    case 'System':
      return `Who owns ${name} and which decisions affect it?`;
    case 'Ticket':
      return `Which decision is based on ${String(p.ticket_id ?? name)}?`;
    case 'Meeting':
      return `What was decided in "${name}"?`;
    default:
      return `Which decisions involve ${name}?`;
  }
}

interface InspectorRow {
  label: string;
  value: React.ReactNode;
}

function describeNode(
  node: GraphNode,
  statusById: Map<string, StatusKind>,
  degree: number
): InspectorRow[] {
  const p = node.properties ?? {};
  const str = (v: unknown) => (typeof v === 'string' && v ? v : null);
  const rows: InspectorRow[] = [];
  const add = (label: string, value: React.ReactNode | null) => {
    if (value !== null && value !== '') rows.push({ label, value });
  };

  switch (node.label) {
    case 'Decision': {
      const status = statusById.get(node.id) ?? 'active';
      add(
        'Status',
        <span className="inline-flex items-center gap-1.5">
          <StatusIcon status={status} size={13} />
          {STATUS_LABEL[status]}
        </span>
      );
      add('Date', formatLongDate(str(p.decided_on)) || null);
      break;
    }
    case 'Person':
      add('Role', str(p.role));
      add('Status', isPersonActive(node) ? 'Active' : `Left ${formatLongDate(str(p.leave_date)) || ''}`.trim());
      break;
    case 'System':
      add('Type', str(p.system_type));
      add('Vendor', str(p.vendor));
      add('Status', str(p.status));
      break;
    case 'Ticket':
      add('Status', str(p.status));
      add('Opened', formatLongDate(str(p.opened)) || null);
      add('Closed', formatLongDate(str(p.closed)) || null);
      add('System', str(p.system));
      break;
    case 'Meeting':
      add('Date', formatLongDate(str(p.date)) || null);
      add('File', str(p.file_name));
      break;
    case 'Project':
      add('Status', str(p.status));
      add('About', str(p.description));
      break;
    case 'Team':
      add('Department', str(p.department));
      break;
    default:
      break;
  }
  rows.push({ label: 'Degree', value: `${degree} ${degree === 1 ? 'edge' : 'edges'}` });
  return rows;
}

const EDGE_PREVIEW = 12;

/** Dedicated page for a node, when one exists. */
function pageHref(node: GraphNode): string | null {
  if (node.label === 'Decision') return decisionHref(decisionCode(node) ?? node.id);
  if (node.label === 'System') return systemHref(nodeTitle(node));
  if (node.label === 'Person') return personHref(nodeTitle(node));
  return null;
}

const Inspector: React.FC<{
  node: GraphNode | undefined;
  index: GraphIndex;
  statusById: Map<string, StatusKind>;
  onFocus: (id: string) => void;
}> = ({ node, index, statusById, onFocus }) => {
  const [showAll, setShowAll] = useState(false);
  useEffect(() => setShowAll(false), [node?.id]);

  if (!node) {
    return (
      <SidePanel label="Selected node" className="bg-surface">
        <p className="m-0 text-muted">Select a node to see its properties and connections.</p>
      </SidePanel>
    );
  }

  const edges = [
    ...(index.outgoing.get(node.id) ?? []).map((e) => ({
      relation: e.type,
      incoming: false,
      other: index.byId.get(e.target),
    })),
    ...(index.incoming.get(node.id) ?? []).map((e) => ({
      relation: e.type,
      incoming: true,
      other: index.byId.get(e.source),
    })),
  ].filter((e) => e.other);
  const shown = showAll ? edges : edges.slice(0, EDGE_PREVIEW);
  const rows = describeNode(node, statusById, edges.length);
  const id = node.label === 'Decision' ? decisionCode(node) : null;
  const decidedBy =
    node.label === 'Decision'
      ? (index.outgoing.get(node.id) ?? [])
          .filter((e) => e.type === 'decided_by')
          .map((e) => index.byId.get(e.target))[0]
      : undefined;

  return (
    <SidePanel label="Selected node" className="bg-surface">
      <div className="flex items-center justify-between">
        <span className="text-muted">{node.label}</span>
        <span className="text-muted">{id ?? (node.label === 'Ticket' ? String(node.properties?.ticket_id ?? '') : '')}</span>
      </div>
      <h2 className="m-0 text-xl font-semibold">{nodeTitle(node)}</h2>
      <PropertyList labelWidth={90}>
        {decidedBy && (
          <Property label="Decided by">
            <Avatar name={nodeTitle(decidedBy)} size={18} active={isPersonActive(decidedBy)} />
            {nodeTitle(decidedBy)}
          </Property>
        )}
        {rows.map((row) => (
          <Property key={row.label} label={row.label}>
            {row.value}
          </Property>
        ))}
      </PropertyList>
      <div className="h-px bg-divider" />
      <div className="flex flex-col gap-0.5">
        <h3 className="m-0 pb-1.5 text-sm font-normal text-muted">Edges</h3>
        {edges.length === 0 && <span className="text-muted">No connections</span>}
        <ul className="m-0 flex list-none flex-col p-0">
          {shown.map((e, i) => (
            <li key={`${e.relation}-${e.other!.id}-${i}`}>
              <button
                type="button"
                onClick={() => onFocus(e.other!.id)}
                title="Focus graph here"
                className="flex h-7 w-full items-center justify-between gap-3 rounded-control border-0 bg-transparent px-1 text-left hover:bg-subtle"
              >
                <span className="shrink-0 text-muted">
                  {e.incoming && (
                    <>
                      <span aria-hidden="true">← </span>
                      <span className="sr-only">incoming </span>
                    </>
                  )}
                  {e.relation}
                </span>
                <span className="min-w-0 truncate">{nodeTitle(e.other!)}</span>
              </button>
            </li>
          ))}
        </ul>
        {edges.length > EDGE_PREVIEW && (
          <button
            type="button"
            onClick={() => setShowAll((s) => !s)}
            className="mt-1 self-start border-0 bg-transparent p-0 text-accent hover:underline"
          >
            {showAll ? 'Show fewer' : `Show all ${edges.length}`}
          </button>
        )}
      </div>
      {pageHref(node) && (
        <Link to={pageHref(node)!} className={`${btnOutline} h-[30px] w-full`}>
          Open {node.label.toLowerCase()} page
        </Link>
      )}
      <Link to={askHref(askAbout(node))} className={`${btnPrimary} w-full`}>
        Ask about this
      </Link>
    </SidePanel>
  );
};

export const GraphPage: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const graphQuery = useGraph();
  const decisionsQuery = useDecisions();
  const [hops, setHops] = useState<Hops>(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [fitSignal, setFitSignal] = useState(0);
  const [copied, setCopied] = useState(false);

  const index = useMemo(
    () => (graphQuery.data ? buildGraphIndex(graphQuery.data) : undefined),
    [graphQuery.data]
  );
  const statusById = useMemo(() => {
    const map = new Map<string, StatusKind>();
    for (const d of decisionsQuery.data ?? []) map.set(d.id, healthToStatus(d.health));
    return map;
  }, [decisionsQuery.data]);

  const hidden = useMemo(() => hiddenTypesFromParams(params), [params]);

  const defaultFocus = useMemo(() => {
    if (!index) return undefined;
    const conflict = index.nodes.find(
      (n) => n.label === 'Decision' && statusById.get(n.id) === 'conflict'
    );
    return conflict ?? index.nodes.find((n) => n.label === 'Decision') ?? index.nodes[0];
  }, [index, statusById]);

  const nodeParam = params.get('node');
  // No ?node: the whole company map. With ?node (or after "Focus"): that node's neighbourhood.
  const focusMode = nodeParam !== null;
  const focus = (nodeParam && index?.find(nodeParam)) || defaultFocus;

  const visible = useMemo(
    () => (index && focus ? neighborhood(index, focus.id, hops, hidden) : { nodes: [], edges: [] }),
    [index, focus, hops, hidden]
  );
  const elements = useMemo(() => toCytoscapeElements(visible, statusById), [visible, statusById]);

  const selected = (selectedId && index?.byId.get(selectedId)) || (focusMode ? focus : undefined);

  // Company map: every node of a shown type, with the edges between them
  const mapGraph = useMemo(() => {
    if (!index) return { nodes: [], edges: [] };
    const nodes = index.nodes.filter((n) => !hidden.has(n.label));
    const keep = new Set(nodes.map((n) => n.id));
    return { nodes, edges: index.edges.filter((e) => keep.has(e.source) && keep.has(e.target)) };
  }, [index, hidden]);
  const mapElements = useMemo(() => toMapElements(mapGraph, statusById), [mapGraph, statusById]);
  const [healthOverlay, setHealthOverlay] = useState(true);
  const [search, setSearch] = useState('');
  const [revealId, setRevealId] = useState<string | null>(null);
  const matches = useMemo(() => searchNodes(mapGraph.nodes, search), [mapGraph.nodes, search]);

  const showMap = () => {
    const next = new URLSearchParams(params);
    next.delete('node');
    next.delete('hide');
    setParams(next, { replace: true });
  };
  const showFocus = () => {
    const target = selectedId ? index?.byId.get(selectedId) : undefined;
    const next = new URLSearchParams(params);
    next.set('node', (target ?? defaultFocus)?.id ?? '');
    next.delete('hide');
    setParams(next, { replace: true });
  };

  const focusOn = (id: string) => {
    const next = new URLSearchParams(params);
    next.set('node', id);
    setParams(next, { replace: true });
    setSelectedId(id);
  };

  useEffect(() => {
    setSelectedId(null);
  }, [focus?.id]);

  const copyCypher = async () => {
    if (!focus) return;
    try {
      await navigator.clipboard.writeText(buildCypher(focus, hops));
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  const atMax = hops === 'all';
  const header = (
    <>
      <span>Explore</span>
      {!focusMode && index && (
        <>
          <span aria-hidden="true">/</span>
          <h1 className="m-0 truncate text-sm font-medium text-text">Company map</h1>
          <span className="ml-1.5 inline-flex h-5 shrink-0 items-center whitespace-nowrap rounded-[4px] border border-border px-1.5 text-[11px]">
            {mapGraph.nodes.length} nodes
          </span>
        </>
      )}
      {focusMode && focus && (
        <>
          <span aria-hidden="true">/</span>
          <h1 className="m-0 truncate text-sm font-medium text-text">{nodeTitle(focus)}</h1>
          <span className="ml-1.5 inline-flex h-5 shrink-0 items-center whitespace-nowrap rounded-[4px] border border-border px-1.5 text-[11px]">
            {hopsLabel(hops)}
          </span>
        </>
      )}
    </>
  );

  const actions = (
    <>
      <div role="group" aria-label="View" className="inline-flex">
        <button type="button" aria-pressed={!focusMode} onClick={showMap} className={`${btnOutline} rounded-r-none ${!focusMode ? 'bg-hover font-medium text-text' : ''}`}>
          Map
        </button>
        <button type="button" aria-pressed={focusMode} onClick={showFocus} className={`${btnOutline} -ml-px rounded-l-none ${focusMode ? 'bg-hover font-medium text-text' : ''}`}>
          Focus
        </button>
      </div>
      {focusMode && (
        <button
          type="button"
          onClick={() => setHops(atMax ? 1 : NEXT_HOPS[String(hops)])}
          className={btnOutline}
        >
          {atMax ? 'Collapse' : 'Expand'}
        </button>
      )}
      <button type="button" onClick={() => setFitSignal((n) => n + 1)} className={btnOutline}>
        Fit
      </button>
      {focusMode && (
        <button type="button" onClick={copyCypher} className={btnOutline} disabled={!focus}>
          {copied ? 'Copied' : 'Copy Cypher'}
        </button>
      )}
      <span role="status" className="sr-only">
        {copied ? 'Cypher query copied to clipboard' : ''}
      </span>
    </>
  );

  const body = (() => {
    if (graphQuery.isLoading) {
      return (
        <div role="status" aria-label="Loading graph" className="flex h-full min-h-[420px] items-center justify-center bg-panel">
          <div className="skeleton h-8 w-40 rounded-control" />
        </div>
      );
    }
    if (graphQuery.isError || !index) {
      return (
        <div role="alert" className="m-5 flex flex-col items-start gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg p-3">
          <span className="font-medium text-status-conflict-text">Could not load the graph</span>
          <span className="text-text-2">{graphQuery.error?.message}</span>
          <button type="button" className={btnOutline} onClick={() => graphQuery.refetch()}>
            Retry
          </button>
        </div>
      );
    }
    if (index.nodes.length === 0) {
      return (
        <div role="status" className="m-5 flex max-w-prose flex-col items-start gap-2 rounded-panel border border-divider bg-subtle p-4">
          <h2 className="m-0 text-lg font-semibold">The map is empty</h2>
          <p className="m-0 text-muted">Nothing has been added to this organization yet. Add a source and its decisions, people and systems appear here.</p>
        </div>
      );
    }
    if (!focusMode) {
      const legendTypes = [...new Set(mapGraph.nodes.map((n) => n.label))];
      return (
        <div className="flex h-full flex-col">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-divider bg-surface px-5 py-2">
            <div className="relative">
              <label htmlFor="map-search" className="sr-only">
                Find a node
              </label>
              <input
                id="map-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Find a node…"
                autoComplete="off"
                className="h-7 w-[200px] rounded-control border border-border bg-surface px-2 text-sm text-text placeholder:text-muted focus-visible:border-accent"
              />
              {matches.length > 0 && (
                <ul aria-label="Matching nodes" className="absolute left-0 top-8 z-20 m-0 flex w-[260px] list-none flex-col rounded-panel border border-border bg-surface p-1 shadow-composer">
                  {matches.map((n) => (
                    <li key={n.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedId(n.id);
                          setRevealId(n.id);
                          setSearch('');
                        }}
                        className="flex h-7 w-full items-center gap-2 rounded-control px-2 text-left text-sm hover:bg-hover"
                      >
                        <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full" style={{ background: TYPE_COLOR[n.label] }} />
                        <span className="min-w-0 flex-1 truncate">{nodeTitle(n)}</span>
                        <span className="shrink-0 text-xs text-muted">{n.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <label className="flex items-center gap-2 text-text-2">
              <input type="checkbox" checked={healthOverlay} onChange={(e) => setHealthOverlay(e.target.checked)} className="m-0 h-3.5 w-3.5 accent-[#4F5BD5]" />
              Health overlay
            </label>
            <ul aria-label="Legend" className="m-0 flex list-none flex-wrap items-center gap-x-3 gap-y-1 p-0 text-xs text-muted">
              {legendTypes.map((t) => (
                <li key={t} className="inline-flex items-center gap-1.5">
                  <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLOR[t] ?? '#8A8E95' }} />
                  {t}
                </li>
              ))}
              {healthOverlay && (
                <>
                  <li className="inline-flex items-center gap-1.5">
                    <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: '#D9363E' }} />
                    Conflict
                  </li>
                  <li className="inline-flex items-center gap-1.5">
                    <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border-2 border-dashed" style={{ borderColor: '#9A9DA4' }} />
                    Superseded
                  </li>
                </>
              )}
              <li>Size is connections</li>
            </ul>
          </div>
          <div className="min-h-[420px] flex-1 min-[900px]:min-h-[560px]">
            <CompanyMap
              elements={mapElements}
              selectedId={selected?.id ?? null}
              onSelect={setSelectedId}
              healthOverlay={healthOverlay}
              fitSignal={fitSignal}
              revealId={revealId}
              ariaLabel={`Company map: ${mapGraph.nodes.length} nodes and ${mapGraph.edges.length} edges. Colour is node type, size is number of connections.`}
            />
          </div>
          <ul aria-label="Nodes on the map" className="sr-only">
            {mapGraph.nodes.slice(0, 120).map((n) => (
              <li key={n.id}>
                <button type="button" onClick={() => setSelectedId(n.id)}>
                  {n.label}: {nodeTitle(n)}
                </button>
              </li>
            ))}
          </ul>
          <p className="m-0 border-t border-divider bg-surface px-5 py-2 text-xs text-muted">
            Showing {mapGraph.nodes.length} of {index.nodes.length} nodes and {mapGraph.edges.length} of {index.edges.length} edges.
            {hidden.size > 0 && ` Hidden: ${[...hidden].join(', ')} (change in the sidebar).`} Click a node to light up its neighbours.
          </p>
        </div>
      );
    }
    return (
      <div className="flex h-full flex-col">
        <div className="min-h-[420px] flex-1 min-[900px]:min-h-[560px]">
          <CytoscapeGraph
            elements={elements}
            focusId={focus?.id ?? null}
            selectedId={selected?.id ?? null}
            onSelect={setSelectedId}
            fitSignal={fitSignal}
            ariaLabel={`Graph of ${visible.nodes.length} nodes and ${visible.edges.length} edges around ${focus ? nodeTitle(focus) : 'the selection'}`}
          />
        </div>
        <ul aria-label="Nodes in view" className="sr-only">
          {visible.nodes.slice(0, 80).map((n) => (
            <li key={n.id}>
              <button type="button" onClick={() => setSelectedId(n.id)}>
                {n.label}: {nodeTitle(n)}
              </button>
            </li>
          ))}
        </ul>
        <p className="m-0 border-t border-divider bg-surface px-5 py-2 text-xs text-muted">
          Showing {visible.nodes.length} of {index.nodes.length} nodes and {visible.edges.length}{' '}
          of {index.edges.length} edges.
        </p>
      </div>
    );
  })();

  return (
    <PageFrame
      header={header}
      actions={actions}
      panel={
        index ? (
          <Inspector node={selected} index={index} statusById={statusById} onFocus={focusMode ? focusOn : setSelectedId} />
        ) : undefined
      }
    >
      {body}
    </PageFrame>
  );
};
