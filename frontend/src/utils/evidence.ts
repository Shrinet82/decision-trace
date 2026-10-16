import type { AskResponse, GraphEdge, GraphNode } from '../api/types';
import { decisionCode, nodeTitle } from './model';

export interface EvidenceRow {
  /** Node type shown in the left column: Ticket, Meeting, Decision, System, Person. */
  kind: string;
  name: string;
  /** DEC-NN code (decision rows only). */
  code: string | null;
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
    code: node.label === 'Decision' ? decisionCode(node) : null,
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
