import type { components, paths } from './schema';

type Schemas = components['schemas'];

export type AskRequest = Schemas['AskRequest'];
export type Citation = Schemas['Citation'];
export type DecisionSummary = Schemas['DecisionSummary'];

/**
 * The generated OpenAPI types mark every field with a server-side default as
 * optional. The API always sends them, so these wrappers make them required.
 */
export type GraphNode = Omit<Schemas['GraphNode'], 'properties'> & {
  properties: Record<string, unknown>;
};
export type GraphEdge = Omit<Schemas['GraphEdge'], 'properties'> & {
  properties: Record<string, unknown>;
};
export type GraphPath = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  omitted_count: number;
};
export type GraphResponse = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
};
export type AskResponse = {
  answer: string;
  citations: Citation[];
  people: string[];
  graph_path: GraphPath;
};
export type SourceRef = Schemas['SourceRef'];
export type DecisionDetail = Omit<
  Schemas['DecisionDetail'],
  'people' | 'systems' | 'sources' | 'supersedes' | 'superseded_by' | 'contradicts'
> & {
  people: string[];
  systems: string[];
  sources: SourceRef[];
  supersedes: string[];
  superseded_by: string[];
  contradicts: string[];
};

export type HealthStatus = 'active' | 'superseded' | 'contradicted' | 'possibly_stale';

export type Paths = paths;
