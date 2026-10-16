import type { components } from './schema';

type Schemas = components['schemas'];

/**
 * The generated OpenAPI types mark every field with a server-side default as optional. The API
 * always sends them, so DeepFilled makes them required (recursively) for the app.
 */
type DeepFilled<T> = T extends (infer U)[]
  ? DeepFilled<U>[]
  : T extends object
    ? { [K in keyof T]-?: DeepFilled<Exclude<T[K], undefined>> }
    : T;

export type AskRequest = Schemas['AskRequest'];
export type Citation = Schemas['Citation'];
export type DecisionSummary = DeepFilled<Schemas['DecisionSummary']>;
export type GraphNode = DeepFilled<Schemas['GraphNode']>;
export type GraphEdge = DeepFilled<Schemas['GraphEdge']>;
export type GraphPath = DeepFilled<Schemas['GraphPath']>;
export type GraphResponse = DeepFilled<Schemas['GraphResponse']>;
export type AskResponse = DeepFilled<Schemas['AskResponse']>;
/**
 * `text` (verbatim body excerpt, at most 1,500 chars) is added by the Phase 2 API. Declared here by
 * hand until schema.d.ts is regenerated; the intersection stays valid afterwards.
 */
export type SourceRef = DeepFilled<Schemas['SourceDetail']> & { text?: string | null };
export type PersonRef = DeepFilled<Schemas['PersonRef']>;
export type DecisionRef = DeepFilled<Schemas['DecisionRef']>;
export type LineageItem = DeepFilled<Schemas['LineageItem']>;
export type CypherTrace = DeepFilled<Schemas['CypherTraceOut']>;
export type DecisionDetail = Omit<DeepFilled<Schemas['DecisionDetail']>, 'sources'> & {
  sources: SourceRef[];
};
export type SystemSummary = DeepFilled<Schemas['SystemSummary']>;
export type SystemDetail = DeepFilled<Schemas['SystemDetail']>;
export type PersonSummary = DeepFilled<Schemas['PersonSummary']>;
export type PersonDetail = DeepFilled<Schemas['PersonDetail']>;

export type HealthStatus = 'active' | 'superseded' | 'contradicted' | 'possibly_stale';

/* ---------------------------------------------------------------------------------------------
 * Live ingest (Phase 2). Hand-written: these endpoints stream server-sent events, which the
 * OpenAPI generator does not describe.
 * ------------------------------------------------------------------------------------------- */

export type IngestSourceType = 'meeting' | 'ticket' | 'announcement';

export interface IngestRequest {
  type: IngestSourceType;
  title: string;
  /** YYYY-MM-DD */
  date: string;
  /** 1..5000 characters */
  text: string;
  participants?: string[];
}

export const INGEST_STEPS = [
  'reading',
  'extracting_decisions',
  'extracting_people',
  'matching',
  'linking',
  'writing',
  'health',
] as const;

export type IngestStepKey = (typeof INGEST_STEPS)[number];
export type IngestStepStatus = 'running' | 'done' | 'skipped' | 'error';

export interface IngestStepEvent {
  step: IngestStepKey;
  status: IngestStepStatus;
  label: string;
  detail?: string;
}

export type IngestNodeLabel = 'Decision' | 'Person' | 'System' | 'Meeting' | 'Ticket' | 'Document';

export interface IngestGraphNode {
  /** `Label:key`, the same convention as the decision subgraph. */
  id: string;
  label: IngestNodeLabel;
  name: string;
  decision_code?: string;
  /** "context" is an existing neighbour shown for orientation. */
  change: 'added' | 'changed' | 'context';
}

export interface IngestGraphEdge {
  source: string;
  target: string;
  type: string;
  change: 'added' | 'context';
}

export interface IngestGraphEvent {
  nodes: IngestGraphNode[];
  edges: IngestGraphEdge[];
}

export interface IngestStatusChange {
  id: string;
  decision_code: string;
  title: string;
  before: HealthStatus;
  after: HealthStatus;
}

export interface IngestDiff {
  ingest_id: string;
  ingested_at: string;
  source: { id: string; label: string; title: string };
  nodes_added: { id: string; label: string; name: string; decision_code?: string }[];
  edges_added: { source: string; target: string; type: string; reason?: string }[];
  status_changes: IngestStatusChange[];
  person_changes: { name: string; field: 'departed'; before: boolean; after: boolean }[];
  orphan_changes: { system: string; before: boolean; after: boolean }[];
  links: {
    new_code: string;
    existing_code: string;
    relation: 'supersedes' | 'contradicts' | 'none';
    reason: string;
  }[];
  /** Server text such as "1 new decision · 2 status changes · conflict resolved". */
  summary: string;
}

export interface IngestErrorEvent {
  message: string;
  step?: IngestStepKey | string;
}

export type IngestEvent =
  | { event: 'step'; data: IngestStepEvent }
  | { event: 'graph'; data: IngestGraphEvent }
  | { event: 'diff'; data: IngestDiff }
  | { event: 'error'; data: IngestErrorEvent };

export interface ChangeEntry {
  id: string;
  kind: 'ingest' | 'reset';
  title: string;
  type?: string;
  created_at: string;
  summary: string;
  diff?: IngestDiff;
}

export interface ResetResult {
  removed_nodes: number;
  removed_edges: number;
  restored_properties: number;
  nodes: number;
  edges: number;
}
