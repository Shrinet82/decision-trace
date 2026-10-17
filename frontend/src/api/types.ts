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

/* ---------------------------------------------------------------------------------------------
 * Streamed Ask (Phase 3). POST /ask/stream emits these server-sent events; POST /ask returns the
 * `done` payload. Hand-written for the same reason as the ingest types above.
 * ------------------------------------------------------------------------------------------- */

export type AskIntent = 'why' | 'impact' | 'expertise' | 'status' | 'other';
export const ASK_STEPS = ['understanding', 'matching', 'traversal', 'health', 'composing'] as const;
export type AskStepKey = (typeof ASK_STEPS)[number];

export interface MatchedEntity {
  label: 'Person' | 'System' | 'Decision';
  name: string;
  id?: string | null;
  decision_code?: string | null;
}

export interface AskStepEvent {
  step: AskStepKey;
  status: 'running' | 'done' | 'skipped' | 'error';
  label: string;
  ms?: number;
  detail?: string | null;
  intent?: AskIntent;
  focus?: string | null;
  entities?: MatchedEntity[];
}

export interface AskQueryEvent {
  step: string;
  name: string;
  query: string;
  params: Record<string, unknown>;
  rows: number;
  ms: number;
}

export interface SectionItem {
  kind: 'decision' | 'person' | 'system' | 'team' | 'project' | 'ticket' | 'meeting';
  name: string;
  id?: string | null;
  code?: string | null;
  health?: HealthStatus | null;
  detail?: string | null;
  role?: string | null;
  departed?: boolean;
  leave_date?: string | null;
  status?: string | null;
  date?: string | null;
}

export interface AnswerSection {
  key: string;
  title: string;
  items: SectionItem[];
  total: number;
}

export interface Expert {
  name: string;
  role?: string | null;
  departed: boolean;
  leave_date?: string | null;
  score: number;
  evidence: { decided: number; owns: number; meetings: number; tickets: number };
  decisions: string[];
  meetings: string[];
  tickets: string[];
}

export interface AskTraceStep {
  step: AskStepKey;
  label: string;
  status: 'done' | 'skipped' | 'error';
  ms: number;
  detail?: string | null;
}

export interface AskTrace {
  steps: AskTraceStep[];
  queries: AskQueryEvent[];
  total_ms: number;
}

export interface AskPathEvent {
  intent: AskIntent;
  graph_path: GraphPath;
  primary_decision_id: string | null;
  sections: AnswerSection[];
  experts: Expert[];
}

/** The full result: AskResponse plus the Phase 3 fields (absent in older fixtures). */
export type AskResult = AskResponse & {
  intent?: AskIntent;
  entities?: MatchedEntity[];
  sections?: AnswerSection[];
  experts?: Expert[];
  trace?: AskTrace | null;
};

export type AskStreamEvent =
  | { event: 'step'; data: AskStepEvent }
  | { event: 'query'; data: AskQueryEvent }
  | { event: 'path'; data: AskPathEvent }
  | { event: 'token'; data: { text: string } }
  | { event: 'done'; data: AskResult }
  | { event: 'error'; data: { message: string } };

/* Sources ------------------------------------------------------------------------------------ */

export type SourceKind = 'ticket' | 'meeting' | 'document' | 'person' | 'team' | 'project' | 'system';

export interface SourceItem {
  kind: SourceKind;
  key: string;
  title: string;
  detail?: string | null;
  date?: string | null;
  linked_decisions: number;
  demo: boolean;
}

export interface SourceList {
  items: SourceItem[];
  counts: Partial<Record<SourceKind, number>>;
}

export interface SourceDocument {
  kind: SourceKind;
  key: string;
  title: string;
  date?: string | null;
  status?: string | null;
  text?: string | null;
  fields: Record<string, unknown>;
  decisions: {
    id: string;
    decision_code?: string | null;
    title: string;
    health: HealthStatus;
    quote?: string | null;
  }[];
  people: { name: string; relation: string; role?: string | null; departed: boolean }[];
  systems: string[];
  related: { label: string; name: string; relation: string }[];
  demo: boolean;
}

export interface DemoStatus {
  has_demo_data: boolean;
  tagged_nodes: number;
  tagged_edges: number;
  last_ingest_at: string | null;
  resets_at: string | null;
  seconds_left: number | null;
  auto_reset_minutes: number;
}
