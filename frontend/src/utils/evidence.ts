import type { AskResponse, GraphEdge, GraphNode } from '../api/types';
import { nodeTitle, type StatusKind } from './model';

export interface EvidenceRow {
  /** Node type shown in the left column: Ticket, Meeting, Decision, System, Person. */
  kind: string;
  name: string;
  detail: string;
  /** Relation of this row to the main decision, e.g. "based on". */
  relation: string | null;
  isMain: boolean;
  nodeId: string;
  node: GraphNode;
}

export interface EvidencePath {
  rows: EvidenceRow[];
  edgeCount: number;
}

const RELATION_LABEL: Record<string, string> = {
  based_on: 'based on',
  supersedes: 'supersedes',
  contradicts: 'conflicts with',
  about_system: 'affects',
  decided_by: 'decided by',
};

/**
 * The decision the answer is mainly about. Scores each decision in the path:
 * +2 if its title is quoted in the answer, +1 if it is based on a cited source
 * (earlier citations win ties), -1.5 if it is already superseded.
 */
export function pickMainDecision(
  response: AskResponse,
  statusById?: Map<string, StatusKind>
): GraphNode | undefined {
  const { nodes, edges } = response.graph_path;
  const decisions = nodes.filter((n) => n.label === 'Decision');
  if (decisions.length === 0) return undefined;

  const byId = new Map(nodes.map((n) => [n.id, n]));
  const answer = response.answer.toLowerCase();

  // Earliest citation index each decision is based on.
  const citedAt = new Map<string, number>();
  response.citations.forEach((citation, ci) => {
    for (const edge of edges) {
      if (edge.type !== 'based_on') continue;
      const target = byId.get(edge.target);
      const source = byId.get(edge.source);
      if (!target || source?.label !== 'Decision') continue;
      const p = target.properties ?? {};
      if (target.id === citation.id || p.ticket_id === citation.id || p.title === citation.id) {
        if (!citedAt.has(source.id)) citedAt.set(source.id, ci);
      }
    }
  });

  let best: GraphNode | undefined;
  let bestScore = -Infinity;
  for (const d of decisions) {
    // The model often quotes a shortened title, so match on the first five words.
    const lead = String(d.properties?.title ?? '').toLowerCase().split(/\s+/).slice(0, 5).join(' ');
    let score = 0;
    if (lead.split(' ').length >= 3 && answer.includes(lead)) score += 2;
    if (citedAt.has(d.id)) score += 1 - 0.01 * (citedAt.get(d.id) ?? 0);
    if (statusById?.get(d.id) === 'superseded') score -= 1.5;
    if (score > bestScore) {
      best = d;
      bestScore = score;
    }
  }
  return best;
}

function describe(node: GraphNode): { name: string; detail: string } {
  const p = node.properties ?? {};
  switch (node.label) {
    case 'Ticket':
      return { name: String(p.ticket_id ?? node.id), detail: String(p.title ?? '') };
    case 'Meeting':
      return { name: String(p.title ?? node.id), detail: String(p.date ?? p.meeting_date ?? '') };
    case 'Person':
      return { name: nodeTitle(node), detail: String(p.role ?? '') };
    default:
      return { name: nodeTitle(node), detail: '' };
  }
}

/**
 * Builds the vertical evidence list around the main decision from the real
 * graph_path edges that touch it. Sources come first, then the decision, then
 * related decisions, the system, and the decider.
 */
export function buildEvidencePath(response: AskResponse, mainId: string, maxRows = 10): EvidencePath {
  const { nodes, edges } = response.graph_path;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const main = byId.get(mainId);
  if (!main) return { rows: [], edgeCount: 0 };

  const touching: { edge: GraphEdge; other: GraphNode; outgoing: boolean }[] = [];
  for (const edge of edges) {
    if (edge.source === mainId && byId.has(edge.target)) {
      touching.push({ edge, other: byId.get(edge.target)!, outgoing: true });
    } else if (edge.target === mainId && byId.has(edge.source)) {
      touching.push({ edge, other: byId.get(edge.source)!, outgoing: false });
    }
  }

  const relationOf = (t: (typeof touching)[number]): string => {
    if (t.edge.type === 'supersedes' && !t.outgoing) return 'superseded by';
    return RELATION_LABEL[t.edge.type] ?? t.edge.type.replace(/_/g, ' ');
  };

  const rank = (t: (typeof touching)[number]): number => {
    if (t.edge.type === 'based_on') return t.other.label === 'Ticket' ? 0 : 1;
    if (t.edge.type === 'supersedes' || t.edge.type === 'contradicts') return 3;
    if (t.edge.type === 'about_system') return 4;
    if (t.edge.type === 'decided_by') return 5;
    return 6;
  };
  touching.sort((a, b) => rank(a) - rank(b));

  const toRow = (node: GraphNode, relation: string | null, isMain: boolean): EvidenceRow => ({
    kind: node.label,
    ...describe(node),
    relation,
    isMain,
    nodeId: node.id,
    node,
  });

  const above = touching.filter((t) => rank(t) < 3).map((t) => toRow(t.other, relationOf(t), false));
  const below = touching.filter((t) => rank(t) >= 3).map((t) => toRow(t.other, relationOf(t), false));
  const rows = [...above, toRow(main, null, true), ...below];

  // Keep the main decision; trim the tail if over the cap.
  const capped = rows.length > maxRows ? rows.slice(0, maxRows) : rows;
  return { rows: capped, edgeCount: touching.length };
}
