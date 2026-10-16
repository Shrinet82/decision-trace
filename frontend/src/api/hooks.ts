import { useQuery } from '@tanstack/react-query';
import { ApiError, askQuestion, getDecision, getGraph, listDecisions } from './client';
import type { AskResponse, DecisionDetail, DecisionSummary, GraphResponse } from './types';

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

export function useDecisionDetail(decisionId: string | undefined) {
  return useQuery<DecisionDetail>({
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
