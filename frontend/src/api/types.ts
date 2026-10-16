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
export type SourceRef = DeepFilled<Schemas['SourceDetail']>;
export type PersonRef = DeepFilled<Schemas['PersonRef']>;
export type DecisionRef = DeepFilled<Schemas['DecisionRef']>;
export type LineageItem = DeepFilled<Schemas['LineageItem']>;
export type CypherTrace = DeepFilled<Schemas['CypherTraceOut']>;
export type DecisionDetail = DeepFilled<Schemas['DecisionDetail']>;
export type SystemSummary = DeepFilled<Schemas['SystemSummary']>;
export type SystemDetail = DeepFilled<Schemas['SystemDetail']>;
export type PersonSummary = DeepFilled<Schemas['PersonSummary']>;
export type PersonDetail = DeepFilled<Schemas['PersonDetail']>;

export type HealthStatus = 'active' | 'superseded' | 'contradicted' | 'possibly_stale';
