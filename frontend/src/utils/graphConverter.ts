import type { ElementsDefinition, EdgeDefinition, NodeDefinition } from 'cytoscape';
import type { GraphEdge, GraphNode } from '../api/types';

import { getSystemLine } from '../config/lines';
import { statusSvgString } from './statusSvg';
import { getAvatarTone, getInitials, truncate } from './format';
import {
  isPersonActive,
  nodeTitle,
  type GraphIndex,
  type StatusKind,
} from './model';

export type Hops = 1 | 2 | 3 | 'all';

export interface VisibleGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/**
 * Nodes within `hops` undirected steps of `focusId`, minus hidden node types
 * (the focus node is always kept), and the edges between the survivors.
 */
export function neighborhood(
  index: GraphIndex,
  focusId: string,
  hops: Hops,
  hiddenTypes: Set<string>
): VisibleGraph {
  const reached = new Set<string>();
  if (hops === 'all') {
    for (const n of index.nodes) reached.add(n.id);
  } else if (index.byId.has(focusId)) {
    reached.add(focusId);
    let frontier = [focusId];
    for (let step = 0; step < hops; step += 1) {
      const next: string[] = [];
      for (const id of frontier) {
        const around = [...(index.outgoing.get(id) ?? []), ...(index.incoming.get(id) ?? [])];
        for (const edge of around) {
          const other = edge.source === id ? edge.target : edge.source;
          if (!reached.has(other)) {
            reached.add(other);
            next.push(other);
          }
        }
      }
      frontier = next;
    }
  }

  const nodes = index.nodes.filter(
    (n) => reached.has(n.id) && (n.id === focusId || !hiddenTypes.has(n.label))
  );
  const keep = new Set(nodes.map((n) => n.id));
  const edges = index.edges.filter((e) => keep.has(e.source) && keep.has(e.target));
  return { nodes, edges };
}

/** A Cypher query that returns the neighborhood currently on screen. */
export function buildCypher(focus: GraphNode, hops: Hops): string {
  const depth = hops === 'all' ? '' : `1..${hops}`;
  const key = focus.label === 'Ticket' ? 'ticket_id' : focus.label === 'Decision' ? 'id' : 'name';
  const value = String(focus.properties?.[key] ?? focus.id).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  return `MATCH p = (n:${focus.label} {${key}: '${value}'})-[*${depth}]-() RETURN p`;
}

function svgUri(svg: string): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const STROKE = 'fill="none" stroke="#6B6F76" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';

export function iconFor(node: GraphNode, status: StatusKind): string {
  switch (node.label) {
    case 'Decision':
      return svgUri(statusSvgString(status));
    case 'System': {
      const color = getSystemLine(nodeTitle(node)).color;
      return svgUri(
        `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14"><rect x="3" y="3" width="8" height="8" rx="2" fill="${color}"/></svg>`
      );
    }
    case 'Person': {
      const name = nodeTitle(node);
      const tone = getAvatarTone(name, isPersonActive(node));
      return svgUri(
        `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><circle cx="10" cy="10" r="9" fill="${tone.bg}"/><text x="10" y="13.4" text-anchor="middle" font-size="9" font-weight="600" font-family="Geist, system-ui, sans-serif" fill="${tone.fg}">${getInitials(name)}</text></svg>`
      );
    }
    case 'Ticket':
      return svgUri(
        `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" ${STROKE}><path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z"/></svg>`
      );
    case 'Meeting':
      return svgUri(
        `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" ${STROKE}><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>`
      );
    case 'Team':
      return svgUri(
        `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" ${STROKE}><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 5a3 3 0 0 1 0 6M18 14c1.7.6 3 2.2 3 4"/></svg>`
      );
    default:
      return svgUri(
        `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" ${STROKE}><rect x="4" y="5" width="16" height="14" rx="2"/><path d="M4 10h16"/></svg>`
      );
  }
}

export function displayLabel(node: GraphNode): string {
  const p = node.properties ?? {};
  if (node.label === 'Ticket' && typeof p.ticket_id === 'string') return p.ticket_id;
  return truncate(nodeTitle(node), node.label === 'Decision' ? 30 : 26);
}

export function toCytoscapeElements(
  visible: VisibleGraph,
  statusById: Map<string, StatusKind>
): ElementsDefinition {
  const nodes: NodeDefinition[] = visible.nodes.map((node) => {
    const status = statusById.get(node.id) ?? 'active';
    return {
      data: {
        id: node.id,
        label: displayLabel(node),
        type: node.label,
        status,
        icon: iconFor(node, status),
        inactive: node.label === 'Person' && !isPersonActive(node),
      },
    };
  });

  const edges: EdgeDefinition[] = visible.edges.map((edge, i) => ({
    data: {
      id: `e${i}`,
      source: edge.source,
      target: edge.target,
      type: edge.type,
      label: edge.type,
    },
  }));

  return { nodes, edges };
}
