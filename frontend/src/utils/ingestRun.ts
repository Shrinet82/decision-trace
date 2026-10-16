import type { ElementsDefinition } from 'cytoscape';
import {
  INGEST_STEPS,
  type IngestDiff,
  type IngestErrorEvent,
  type IngestEvent,
  type IngestGraphEdge,
  type IngestGraphEvent,
  type IngestGraphNode,
  type IngestStepKey,
  type IngestStepStatus,
} from '../api/types';
import { truncate } from './format';
import { iconFor } from './graphConverter';

export type StepDisplayStatus = 'pending' | IngestStepStatus;

export interface StepState {
  key: IngestStepKey;
  status: StepDisplayStatus;
  label: string;
  detail?: string;
}

export interface RunState {
  steps: StepState[];
  graph: IngestGraphEvent;
  diff: IngestDiff | null;
  error: IngestErrorEvent | null;
}

export const DEFAULT_STEP_LABELS: Record<IngestStepKey, string> = {
  reading: 'Reading source',
  extracting_decisions: 'Extracting decisions',
  extracting_people: 'Extracting people',
  matching: 'Matching existing entities',
  linking: 'Linking to existing decisions',
  writing: 'Writing to graph',
  health: 'Recomputing decision health',
};

export function initialRun(): RunState {
  return {
    steps: INGEST_STEPS.map((key) => ({ key, status: 'pending', label: DEFAULT_STEP_LABELS[key] })),
    graph: { nodes: [], edges: [] },
    diff: null,
    error: null,
  };
}

const NODE_RANK = { context: 0, changed: 1, added: 2 } as const;
const EDGE_RANK = { context: 0, added: 1 } as const;
const edgeKey = (e: IngestGraphEdge) => `${e.source}|${e.type}|${e.target}`;

/** Accumulates incremental graph events. A node or edge is never downgraded (added stays added). */
export function mergeGraph(graph: IngestGraphEvent, update: IngestGraphEvent): IngestGraphEvent {
  const nodes = new Map<string, IngestGraphNode>(graph.nodes.map((n) => [n.id, n]));
  for (const n of update.nodes ?? []) {
    const prev = nodes.get(n.id);
    const change = prev && NODE_RANK[prev.change] > NODE_RANK[n.change] ? prev.change : n.change;
    nodes.set(n.id, { ...prev, ...n, change });
  }
  const edges = new Map<string, IngestGraphEdge>(graph.edges.map((e) => [edgeKey(e), e]));
  for (const e of update.edges ?? []) {
    const prev = edges.get(edgeKey(e));
    const change = prev && EDGE_RANK[prev.change] > EDGE_RANK[e.change] ? prev.change : e.change;
    edges.set(edgeKey(e), { ...e, change });
  }
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

export function applyIngestEvent(state: RunState, event: IngestEvent): RunState {
  switch (event.event) {
    case 'step': {
      const { step, status, label, detail } = event.data;
      return {
        ...state,
        steps: state.steps.map((s) =>
          s.key === step ? { ...s, status, label: label || s.label, detail: detail ?? s.detail } : s
        ),
      };
    }
    case 'graph':
      return { ...state, graph: mergeGraph(state.graph, event.data) };
    case 'diff':
      return { ...state, diff: event.data };
    case 'error': {
      const failed = event.data.step ?? state.steps.find((s) => s.status === 'running')?.key;
      return {
        ...state,
        error: event.data,
        steps: state.steps.map((s) =>
          s.key === failed || s.status === 'running' ? { ...s, status: 'error' } : s
        ),
      };
    }
    default:
      return state;
  }
}

/** Neutral ring for decisions whose health is not part of the stream. */
const DECISION_ICON = `data:image/svg+xml;utf8,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14"><circle cx="7" cy="7" r="5.6" fill="none" stroke="#6B6F76" stroke-width="1.6"/></svg>'
)}`;

export function miniNodeLabel(n: IngestGraphNode): string {
  if (n.label === 'Decision') {
    return n.decision_code ? `${n.decision_code} · ${truncate(n.name, 26)}` : truncate(n.name, 32);
  }
  return truncate(n.name, 26);
}

/** Cytoscape elements for the ingest mini graph; edges to unknown nodes are dropped. */
export function miniGraphElements(graph: IngestGraphEvent): ElementsDefinition {
  const ids = new Set(graph.nodes.map((n) => n.id));
  return {
    nodes: graph.nodes.map((n) => ({
      data: {
        id: n.id,
        label: miniNodeLabel(n),
        type: n.label,
        change: n.change,
        icon:
          n.label === 'Decision'
            ? DECISION_ICON
            : iconFor({ id: n.id, label: n.label, properties: { name: n.name } }, 'active'),
      },
    })),
    edges: graph.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e, i) => ({
        data: {
          id: `ing${i}`,
          source: e.source,
          target: e.target,
          type: e.type.toLowerCase(),
          change: e.change,
          label: e.type.toLowerCase().replace(/_/g, ' '),
        },
      })),
  };
}
