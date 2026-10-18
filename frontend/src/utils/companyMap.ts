import type { ElementsDefinition } from 'cytoscape';
import type { GraphNode } from '../api/types';
import { truncate } from './format';
import { decisionCode, isPersonActive, nodeTitle, type StatusKind } from './model';
import type { VisibleGraph } from './graphConverter';

/** One colour per node type. Ticket and Document are neutral: they are many and rarely the point. */
export const TYPE_COLOR: Record<string, string> = {
  Decision: '#4F5BD5',
  Person: '#12807A',
  System: '#C98A00',
  Team: '#5A47C8',
  Project: '#C72C7A',
  Meeting: '#6B6F76',
  Document: '#8A8E95',
  Ticket: '#9A9DA4',
};
export const DEFAULT_TYPE_COLOR = '#8A8E95';

/** Types the map hides until asked: there are dozens of tickets for every decision. */
export const DEFAULT_HIDDEN_TYPES = ['Ticket'] as const;

export const MIN_NODE = 14;
export const MAX_NODE = 46;

/** Diameter in pixels from the number of connections (square-root scale, so hubs stand out but fit). */
export function nodeSize(degree: number, maxDegree: number): number {
  if (maxDegree <= 0) return MIN_NODE + 4;
  const t = Math.sqrt(Math.max(0, degree) / maxDegree);
  return Math.round(MIN_NODE + t * (MAX_NODE - MIN_NODE));
}

/** A small stable hash, used so the starting layout (and so the final one) is the same every time. */
export function hashString(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Deterministic start positions: a ring per node type, nodes spread by hash. The force layout
 *  then relaxes these, so the same graph always settles into the same picture. */
export function seedPosition(id: string, type: string, types: string[]): { x: number; y: number } {
  const ring = Math.max(0, types.indexOf(type));
  const radius = 140 + ring * 90;
  const angle = ((hashString(id) % 3600) / 3600) * Math.PI * 2;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export function mapLabel(node: GraphNode): string {
  if (node.label === 'Decision') return decisionCode(node) ?? truncate(nodeTitle(node), 24);
  if (node.label === 'Ticket') return String(node.properties?.ticket_id ?? truncate(nodeTitle(node), 18));
  return truncate(nodeTitle(node), 22);
}

export function degreeMap(graph: VisibleGraph): Map<string, number> {
  const degree = new Map<string, number>();
  for (const n of graph.nodes) degree.set(n.id, 0);
  for (const e of graph.edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  return degree;
}

/** Cytoscape elements for the company map. Edge ids are stable so layouts do not reshuffle. */
export function toMapElements(graph: VisibleGraph, statusById: Map<string, StatusKind>): ElementsDefinition {
  const degree = degreeMap(graph);
  const maxDegree = Math.max(0, ...degree.values());
  const types = [...new Set(graph.nodes.map((n) => n.label))].sort();
  return {
    nodes: graph.nodes.map((n) => {
      const status = n.label === 'Decision' ? (statusById.get(n.id) ?? 'active') : 'active';
      const pos = seedPosition(n.id, n.label, types);
      return {
        data: {
          id: n.id,
          label: mapLabel(n),
          type: n.label,
          status,
          degree: degree.get(n.id) ?? 0,
          size: nodeSize(degree.get(n.id) ?? 0, maxDegree),
          color: TYPE_COLOR[n.label] ?? DEFAULT_TYPE_COLOR,
          inactive: n.label === 'Person' && !isPersonActive(n),
        },
        position: pos,
      };
    }),
    edges: graph.edges.map((e, i) => ({
      data: { id: `m${i}-${e.source}-${e.target}`, source: e.source, target: e.target, type: e.type },
    })),
  };
}

/** Nodes whose title, name, code or ticket id contains the text (case-insensitive), best first. */
export function searchNodes(nodes: GraphNode[], text: string, limit = 8): GraphNode[] {
  const q = text.trim().toLowerCase();
  if (q.length < 2) return [];
  const scored: [number, GraphNode][] = [];
  for (const n of nodes) {
    const hay = [nodeTitle(n), decisionCode(n) ?? '', String(n.properties?.ticket_id ?? '')].map((s) => s.toLowerCase());
    let best: number | null = null;
    for (const h of hay) {
      if (!h) continue;
      const at = h.indexOf(q);
      if (at === -1) continue;
      const score = (at === 0 ? 0 : 1) + (h === q ? -1 : 0);
      best = best === null ? score : Math.min(best, score);
    }
    if (best !== null) scored.push([best, n]);
  }
  scored.sort((a, b) => a[0] - b[0] || nodeTitle(a[1]).localeCompare(nodeTitle(b[1])));
  return scored.slice(0, limit).map(([, n]) => n);
}

/** Node types hidden by the `hide` URL parameter. With no parameter the map hides tickets and the
 *  focus view hides nothing; `hide=none` means the person turned every type back on. */
export function hiddenTypesFromParams(params: URLSearchParams): Set<string> {
  const raw = params.get('hide');
  if (raw === null) return params.has('node') ? new Set() : new Set(DEFAULT_HIDDEN_TYPES);
  return new Set(raw.split(',').filter((t) => t && t !== 'none'));
}

export function hideParamValue(hidden: Set<string>): string {
  return hidden.size > 0 ? [...hidden].join(',') : 'none';
}
