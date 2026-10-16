import type { EdgeDefinition, ElementsDefinition, NodeDefinition } from 'cytoscape';
import type { DecisionDetail, GraphNode } from '../api/types';
import { iconFor } from './graphConverter';
import { truncate } from './format';
import { decisionHref, personHref, systemHref } from './links';
import { healthToStatus } from './model';

export interface LineageNode {
  id: string;
  type: string;
  label: string;
  href: string | null;
  isFocus: boolean;
}

export interface LineageGraph {
  elements: ElementsDefinition;
  nodes: LineageNode[];
  /** Nodes left out to respect the cap. */
  omitted: number;
}

function hrefFor(node: GraphNode): string | null {
  const p = node.properties;
  if (node.label === 'Decision') return decisionHref(String(p.decision_code ?? p.id));
  if (node.label === 'System') return systemHref(String(p.name));
  if (node.label === 'Person') return personHref(String(p.name));
  return null;
}

function labelFor(node: GraphNode): string {
  const p = node.properties;
  if (node.label === 'Decision') {
    const code = p.decision_code ? `${String(p.decision_code)} · ` : '';
    return truncate(`${code}${String(p.title ?? '')}`, 40);
  }
  if (node.label === 'Ticket') return String(p.ticket_id ?? node.id);
  return truncate(String(p.title ?? p.name ?? node.id), 30);
}

/**
 * The focused lineage graph of a decision: its sources, the full supersedes chain both ways and
 * contradicting decisions. Time flows left to right: sources and older decisions on the left,
 * newer ones on the right. Supersedes edges point old -> new ("superseded by"); based_on edges
 * point source -> decision. At most `max` nodes: decisions first, then their sources.
 */
export function buildLineageGraph(detail: DecisionDetail, max = 25): LineageGraph {
  const { lineage } = detail;
  const decisionIds = [
    detail.id,
    ...lineage.superseded_by.map((d) => d.id),
    ...lineage.supersedes.map((d) => d.id),
    ...lineage.contradicts.map((d) => d.id),
    ...lineage.contradicted_by.map((d) => d.id),
  ];
  const byId = new Map(detail.subgraph.nodes.map((n) => [n.id, n]));
  const keep: string[] = [];
  for (const id of decisionIds) {
    const key = `Decision:${id}`;
    if (byId.has(key) && !keep.includes(key)) keep.push(key);
  }
  const decisionKeys = new Set(keep);

  const sourceEdges = detail.subgraph.edges.filter(
    (e) => e.type === 'based_on' && decisionKeys.has(e.source)
  );
  // Focus decision's sources first
  sourceEdges.sort((a, b) => Number(b.source === `Decision:${detail.id}`) - Number(a.source === `Decision:${detail.id}`));
  for (const e of sourceEdges) {
    if (!keep.includes(e.target) && byId.has(e.target)) keep.push(e.target);
  }

  const total = keep.length;
  const kept = new Set(keep.slice(0, max));

  const nodes: NodeDefinition[] = [];
  const list: LineageNode[] = [];
  for (const key of keep.slice(0, max)) {
    const node = byId.get(key)!;
    const status = healthToStatus(String(node.properties.health ?? 'active'));
    const isFocus = key === `Decision:${detail.id}`;
    nodes.push({
      data: {
        id: key,
        label: labelFor(node),
        type: node.label,
        status,
        icon: iconFor(node, status),
        href: hrefFor(node),
      },
    });
    list.push({ id: key, type: node.label, label: labelFor(node), href: hrefFor(node), isFocus });
  }

  const edges: EdgeDefinition[] = [];
  detail.subgraph.edges.forEach((e, i) => {
    if (!kept.has(e.source) || !kept.has(e.target)) return;
    if (e.type === 'based_on') {
      edges.push({ data: { id: `l${i}`, source: e.target, target: e.source, type: 'based_on', label: 'based on' } });
    } else if (e.type === 'supersedes') {
      // a supersedes b  =>  draw b (older) -> a (newer)
      edges.push({ data: { id: `l${i}`, source: e.target, target: e.source, type: 'supersedes', label: 'superseded by' } });
    } else if (e.type === 'contradicts') {
      edges.push({ data: { id: `l${i}`, source: e.source, target: e.target, type: 'contradicts', label: 'contradicts' } });
    }
  });

  return { elements: { nodes, edges }, nodes: list, omitted: Math.max(0, total - max) };
}
