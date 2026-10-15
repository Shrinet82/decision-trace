import type { components, paths } from './schema';

export type AskRequest = components['schemas']['AskRequest'];
export type AskResponse = components['schemas']['AskResponse'];
export type Citation = components['schemas']['Citation'];
export type DecisionDetail = components['schemas']['DecisionDetail'];
export type DecisionSummary = components['schemas']['DecisionSummary'];
export type GraphPath = components['schemas']['GraphPath'];
export type GraphNode = components['schemas']['GraphNode'];
export type GraphEdge = components['schemas']['GraphEdge'];

export type HealthStatus = 'active' | 'superseded' | 'contradicted' | 'possibly_stale';

export type Paths = paths;
