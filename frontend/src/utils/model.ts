import type { DecisionDetail, DecisionSummary, GraphEdge, GraphNode, GraphResponse, HealthStatus } from '../api/types';

export type StatusKind = 'active' | 'conflict' | 'stale' | 'superseded';

export const STATUS_LABEL: Record<StatusKind, string> = {
  active: 'Active',
  conflict: 'Conflict',
  stale: 'Possibly stale',
  superseded: 'Superseded',
};

/** Display order of status groups on the Decisions page. */
export const STATUS_ORDER: StatusKind[] = ['conflict', 'stale', 'active', 'superseded'];

export function healthToStatus(health: HealthStatus | string | undefined): StatusKind {
  switch (health) {
    case 'contradicted':
      return 'conflict';
    case 'possibly_stale':
      return 'stale';
    case 'superseded':
      return 'superseded';
    default:
      return 'active';
  }
}

export function nodeTitle(node: GraphNode): string {
  const p = node.properties ?? {};
  return String(p.title ?? p.name ?? p.ticket_id ?? node.id);
}

/** Short reference used in relation hints: ticket id when known, else a clipped title. */
export function shortRef(ticketId: string | undefined, title: string, max = 32): string {
  if (ticketId) return ticketId;
  return title.length > max ? `${title.slice(0, max - 1).trimEnd()}…` : title;
}

export interface GraphIndex {
  nodes: GraphNode[];
  edges: GraphEdge[];
  byId: Map<string, GraphNode>;
  outgoing: Map<string, GraphEdge[]>;
  incoming: Map<string, GraphEdge[]>;
  countsByLabel: Map<string, number>;
  /** Looks a node up by id, ticket_id, name, or title (the keys /ask uses). */
  find: (key: string) => GraphNode | undefined;
}

export function buildGraphIndex(graph: GraphResponse): GraphIndex {
  const byId = new Map<string, GraphNode>();
  const byKey = new Map<string, GraphNode>();
  const countsByLabel = new Map<string, number>();

  for (const node of graph.nodes) {
    byId.set(node.id, node);
    countsByLabel.set(node.label, (countsByLabel.get(node.label) ?? 0) + 1);
    const p = node.properties ?? {};
    for (const key of [node.id, p.ticket_id, p.name, p.title]) {
      if (typeof key === 'string' && key && !byKey.has(key)) byKey.set(key, node);
    }
  }

  const outgoing = new Map<string, GraphEdge[]>();
  const incoming = new Map<string, GraphEdge[]>();
  for (const edge of graph.edges) {
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    outgoing.get(edge.source)!.push(edge);
    incoming.get(edge.target)!.push(edge);
  }

  return {
    nodes: graph.nodes,
    edges: graph.edges,
    byId,
    outgoing,
    incoming,
    countsByLabel,
    find: (key) => byId.get(key) ?? byKey.get(key),
  };
}

function targets(index: GraphIndex, id: string, type: string): GraphNode[] {
  return (index.outgoing.get(id) ?? [])
    .filter((e) => e.type === type)
    .map((e) => index.byId.get(e.target))
    .filter((n): n is GraphNode => Boolean(n));
}

function sources(index: GraphIndex, id: string, type: string): GraphNode[] {
  return (index.incoming.get(id) ?? [])
    .filter((e) => e.type === type)
    .map((e) => index.byId.get(e.source))
    .filter((n): n is GraphNode => Boolean(n));
}

export function isPersonActive(person: GraphNode): boolean {
  const p = person.properties ?? {};
  return p.is_active !== false;
}

/** People who own a system but have left (is_active false). */
export function ownersWhoLeft(index: GraphIndex, decisionId: string): GraphNode[] {
  const left: GraphNode[] = [];
  for (const system of targets(index, decisionId, 'about_system')) {
    for (const owner of sources(index, system.id, 'owns')) {
      if (!isPersonActive(owner)) left.push(owner);
    }
  }
  return left;
}

/** True if there is at least one owner on record for the decision's system. */
export function hasOwnerOnRecord(index: GraphIndex, decisionId: string): boolean {
  return targets(index, decisionId, 'about_system').some(
    (system) => sources(index, system.id, 'owns').length > 0
  );
}

export interface RelationHint {
  text: string;
  tone: 'muted' | 'stale';
}

export interface DecisionRow {
  id: string;
  title: string;
  status: StatusKind;
  health: HealthStatus;
  healthReason: string;
  system: string | null;
  decidedBy: string | null;
  decidedOn: string | null;
  /** Source ticket id (e.g. TICK-105) when the decision is based on one. */
  ticketId: string | null;
  hint: RelationHint | null;
}

export function sourceTicketId(index: GraphIndex | undefined, decisionId: string): string | null {
  if (!index) return null;
  for (const node of targets(index, decisionId, 'based_on')) {
    const ticketId = node.properties?.ticket_id;
    if (node.label === 'Ticket' && typeof ticketId === 'string') return ticketId;
  }
  return null;
}

function refOf(index: GraphIndex, node: GraphNode): string {
  return shortRef(sourceTicketId(index, node.id) ?? undefined, nodeTitle(node));
}

function relationHint(
  index: GraphIndex,
  summary: DecisionSummary,
  status: StatusKind
): RelationHint | null {
  const id = summary.id;
  const conflicts = [...targets(index, id, 'contradicts'), ...sources(index, id, 'contradicts')];
  const replacedBy = sources(index, id, 'supersedes');
  const replaces = targets(index, id, 'supersedes');

  if (status === 'conflict' && conflicts.length > 0) {
    return { text: `conflicts with ${refOf(index, conflicts[0])}`, tone: 'muted' };
  }
  if (status === 'superseded' && replacedBy.length > 0) {
    return { text: `replaced by ${refOf(index, replacedBy[0])}`, tone: 'muted' };
  }
  if (status === 'stale') {
    if (ownersWhoLeft(index, id).length > 0) {
      return { text: 'owner left the company', tone: 'stale' };
    }
    return { text: 'needs review', tone: 'stale' };
  }
  if (replaces.length > 0) {
    return { text: `supersedes ${refOf(index, replaces[0])}`, tone: 'muted' };
  }
  return null;
}

export function buildDecisionRows(
  decisions: DecisionSummary[],
  index: GraphIndex | undefined
): DecisionRow[] {
  return decisions.map((d) => {
    const status = healthToStatus(d.health);
    return {
      id: d.id,
      title: d.title,
      status,
      health: d.health,
      healthReason: d.health_reason,
      system: d.system ?? null,
      decidedBy: d.decided_by ?? null,
      decidedOn: d.decided_on ?? null,
      ticketId: sourceTicketId(index, d.id),
      hint: index ? relationHint(index, d, status) : null,
    };
  });
}

export function countByStatus(rows: DecisionRow[]): Record<StatusKind, number> {
  const counts: Record<StatusKind, number> = { active: 0, conflict: 0, stale: 0, superseded: 0 };
  for (const row of rows) counts[row.status] += 1;
  return counts;
}

export interface SystemSummary {
  name: string;
  decisionCount: number;
}

/** Systems that at least one decision is about, most-decided first. */
export function systemsWithDecisions(index: GraphIndex): SystemSummary[] {
  const counts = new Map<string, number>();
  for (const node of index.nodes) {
    if (node.label !== 'Decision') continue;
    for (const system of targets(index, node.id, 'about_system')) {
      const name = nodeTitle(system);
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([name, decisionCount]) => ({ name, decisionCount }))
    .sort((a, b) => b.decisionCount - a.decisionCount || a.name.localeCompare(b.name));
}

/** Verbatim evidence quote of a decision that is based on the given source node. */
export function evidenceQuoteForSource(index: GraphIndex, sourceId: string): string | null {
  for (const edge of index.incoming.get(sourceId) ?? []) {
    if (edge.type !== 'based_on') continue;
    const decision = index.byId.get(edge.source);
    const quote = decision?.properties?.evidence_quote;
    if (decision?.label === 'Decision' && typeof quote === 'string' && quote.trim()) {
      return quote.trim();
    }
  }
  return null;
}

export interface ValidityCheck {
  label: string;
  ok: boolean;
}

/** Validity checks shown in the Ask properties panel, derived from health data and the graph. */
export function validityChecks(detail: DecisionDetail, index: GraphIndex | undefined): ValidityCheck[] {
  const checks: ValidityCheck[] = [
    detail.superseded_by.length === 0
      ? { label: 'No newer decision', ok: true }
      : { label: `Superseded by ${detail.superseded_by[0]}`, ok: false },
    detail.contradicts.length === 0
      ? { label: 'No contradictions', ok: true }
      : { label: `Conflicts with ${detail.contradicts[0]}`, ok: false },
  ];
  if (index && hasOwnerOnRecord(index, detail.id)) {
    checks.push(
      ownersWhoLeft(index, detail.id).length === 0
        ? { label: 'Owner still on team', ok: true }
        : { label: 'Owner left the company', ok: false }
    );
  }
  return checks;
}
