import { useQuery, type QueryClient } from '@tanstack/react-query';
import { getCurrentOrg } from '../org/orgState';
import {
  ApiError,
  askQuestion,
  getDecision,
  getAttention,
  getOrg,
  getDemoStatus,
  getSource,
  listSources,
  getGraph,
  getPerson,
  getSystem,
  listChanges,
  listDecisions,
  listPeople,
  listSystems,
} from './client';
import type {
  Attention,
  OrgInfo,
  AskResponse,
  ChangeEntry,
  DecisionDetail,
  DecisionSummary,
  DemoStatus,
  GraphResponse,
  SourceDocument,
  SourceKind,
  SourceList,
  PersonDetail,
  PersonSummary,
  SystemDetail,
  SystemSummary,
} from './types';

const FIVE_MINUTES = 1000 * 60 * 5;

/** Query keys end with the organization, so two organizations never share cached data (and key[0] stays the resource name). */
function orgKey<T extends unknown[]>(key: T): [...T, string] {
  return [...key, getCurrentOrg() ?? 'sample'];
}

export function useDecisions() {
  return useQuery<DecisionSummary[]>({
    queryKey: orgKey(['decisions']),
    queryFn: listDecisions,
    staleTime: FIVE_MINUTES,
  });
}

export function useGraph() {
  return useQuery<GraphResponse>({
    queryKey: orgKey(['graph']),
    queryFn: getGraph,
    staleTime: FIVE_MINUTES,
  });
}

/** A decision page by DEC code, id, or title. */
export function useDecisionDetail(decisionId: string | undefined) {
  return useQuery<DecisionDetail, ApiError>({
    queryKey: orgKey(['decision', decisionId]),
    queryFn: () => getDecision(decisionId!),
    enabled: Boolean(decisionId),
    staleTime: FIVE_MINUTES,
  });
}

export function useAsk(question: string | null) {
  return useQuery<AskResponse, ApiError>({
    queryKey: orgKey(['ask', question]),
    queryFn: () => askQuestion({ question: question! }),
    enabled: Boolean(question && question.trim().length >= 2),
    staleTime: FIVE_MINUTES,
    retry: 1,
  });
}

export function useSystems() {
  return useQuery<SystemSummary[], ApiError>({
    queryKey: orgKey(['systems']),
    queryFn: listSystems,
    staleTime: FIVE_MINUTES,
  });
}

export function useSystem(name: string | undefined) {
  return useQuery<SystemDetail, ApiError>({
    queryKey: orgKey(['system', name?.toLowerCase()]),
    queryFn: () => getSystem(name!),
    enabled: Boolean(name),
    staleTime: FIVE_MINUTES,
    retry: (count, error) => error.status !== 404 && count < 1,
  });
}

export function usePeople() {
  return useQuery<PersonSummary[], ApiError>({
    queryKey: orgKey(['people']),
    queryFn: listPeople,
    staleTime: FIVE_MINUTES,
  });
}

export function usePerson(name: string | undefined) {
  return useQuery<PersonDetail, ApiError>({
    queryKey: orgKey(['person', name?.toLowerCase()]),
    queryFn: () => getPerson(name!),
    enabled: Boolean(name),
    staleTime: FIVE_MINUTES,
    retry: (count, error) => error.status !== 404 && count < 1,
  });
}

/** The change log (ingests and resets), newest first. */
export function useChanges(limit = 20) {
  return useQuery<ChangeEntry[], ApiError>({
    queryKey: orgKey(['changes', limit]),
    queryFn: () => listChanges(limit),
    staleTime: 30_000,
    retry: false,
  });
}

export function useSources() {
  return useQuery<SourceList, ApiError>({
    queryKey: orgKey(['sources']),
    queryFn: listSources,
    staleTime: FIVE_MINUTES,
  });
}

export function useSource(kind: SourceKind | undefined, key: string | undefined) {
  return useQuery<SourceDocument, ApiError>({
    queryKey: orgKey(['source', kind, key]),
    queryFn: () => getSource(kind!, key!),
    enabled: Boolean(kind && key),
    staleTime: FIVE_MINUTES,
    retry: (count, error) => error.status !== 404 && count < 1,
  });
}

/** Demo data presence and the automatic reset time; polled while `enabled` (the drawer is open). */
export function useDemoStatus(enabled: boolean) {
  return useQuery<DemoStatus, ApiError>({
    queryKey: orgKey(['demo-status']),
    queryFn: getDemoStatus,
    enabled,
    refetchInterval: enabled ? 30_000 : false,
    retry: false,
  });
}

/** First query-key segments whose data an ingest or a reset can change. */
export const GRAPH_QUERY_KEYS = [
  'decisions',
  'decision',
  'systems',
  'system',
  'people',
  'person',
  'graph',
  'changes',
  'sources',
  'source',
  'demo-status',
] as const;

/** Refetch everything derived from the graph after an ingest or reset. */
export function invalidateGraphQueries(queryClient: QueryClient): Promise<void> {
  const keys = new Set<string>(GRAPH_QUERY_KEYS);
  return queryClient.invalidateQueries({
    predicate: (query) => keys.has(String(query.queryKey[0])),
  });
}

export function useAttention() {
  return useQuery<Attention, ApiError>({
    queryKey: orgKey(['attention']),
    queryFn: getAttention,
    staleTime: 60_000,
    retry: 1,
  });
}

/** The current organization (name, size). A 404 means it was deleted or expired. */
export function useOrgInfo(slug: string | null) {
  return useQuery<OrgInfo, ApiError>({
    queryKey: ['org', slug ?? 'sample'],
    queryFn: () => getOrg(slug ?? 'sample'),
    staleTime: FIVE_MINUTES,
    retry: (count, error) => error.status !== 404 && count < 1,
  });
}
