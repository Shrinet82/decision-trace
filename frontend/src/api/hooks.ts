import { useQuery } from '@tanstack/react-query';
import {
  ApiError,
  askQuestion,
  getDecision,
  getGraph,
  getPerson,
  getSystem,
  listDecisions,
  listPeople,
  listSystems,
} from './client';
import type {
  AskResponse,
  DecisionDetail,
  DecisionSummary,
  GraphResponse,
  PersonDetail,
  PersonSummary,
  SystemDetail,
  SystemSummary,
} from './types';

const FIVE_MINUTES = 1000 * 60 * 5;

export function useDecisions() {
  return useQuery<DecisionSummary[]>({
    queryKey: ['decisions'],
    queryFn: listDecisions,
    staleTime: FIVE_MINUTES,
  });
}

export function useGraph() {
  return useQuery<GraphResponse>({
    queryKey: ['graph'],
    queryFn: getGraph,
    staleTime: FIVE_MINUTES,
  });
}

/** A decision page by DEC code, id, or title. */
export function useDecisionDetail(decisionId: string | undefined) {
  return useQuery<DecisionDetail, ApiError>({
    queryKey: ['decision', decisionId],
    queryFn: () => getDecision(decisionId!),
    enabled: Boolean(decisionId),
    staleTime: FIVE_MINUTES,
  });
}

export function useAsk(question: string | null) {
  return useQuery<AskResponse, ApiError>({
    queryKey: ['ask', question],
    queryFn: () => askQuestion({ question: question! }),
    enabled: Boolean(question && question.trim().length >= 2),
    staleTime: FIVE_MINUTES,
    retry: 1,
  });
}

export function useSystems() {
  return useQuery<SystemSummary[], ApiError>({
    queryKey: ['systems'],
    queryFn: listSystems,
    staleTime: FIVE_MINUTES,
  });
}

export function useSystem(name: string | undefined) {
  return useQuery<SystemDetail, ApiError>({
    queryKey: ['system', name?.toLowerCase()],
    queryFn: () => getSystem(name!),
    enabled: Boolean(name),
    staleTime: FIVE_MINUTES,
    retry: (count, error) => error.status !== 404 && count < 1,
  });
}

export function usePeople() {
  return useQuery<PersonSummary[], ApiError>({
    queryKey: ['people'],
    queryFn: listPeople,
    staleTime: FIVE_MINUTES,
  });
}

export function usePerson(name: string | undefined) {
  return useQuery<PersonDetail, ApiError>({
    queryKey: ['person', name?.toLowerCase()],
    queryFn: () => getPerson(name!),
    enabled: Boolean(name),
    staleTime: FIVE_MINUTES,
    retry: (count, error) => error.status !== 404 && count < 1,
  });
}
