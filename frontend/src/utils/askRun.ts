import {
  ASK_STEPS,
  type AskIntent,
  type AskPathEvent,
  type AskQueryEvent,
  type AskResult,
  type AskStepKey,
  type AskStreamEvent,
  type MatchedEntity,
} from '../api/types';
import { isNotFoundAnswer } from './answer';

export type AskStepStatus = 'pending' | 'running' | 'done' | 'skipped' | 'error';

export interface AskStepState {
  key: AskStepKey;
  label: string;
  status: AskStepStatus;
  ms?: number;
  detail?: string | null;
}

export interface AskRunState {
  steps: AskStepState[];
  intent: AskIntent | null;
  entities: MatchedEntity[];
  queries: AskQueryEvent[];
  /** Evidence, sections and experts, sent before the answer is composed. */
  path: AskPathEvent | null;
  /** Answer text streamed so far (the final text once `result` arrives). */
  answer: string;
  result: AskResult | null;
  error: string | null;
  totalMs: number | null;
}

export const ASK_STEP_LABELS: Record<AskStepKey, string> = {
  understanding: 'Understanding the question',
  matching: 'Matching people, systems and decisions',
  traversal: 'Traversing the graph',
  health: 'Checking decision health',
  composing: 'Composing the answer',
};

export function initialAskRun(): AskRunState {
  return {
    steps: ASK_STEPS.map((key) => ({ key, label: ASK_STEP_LABELS[key], status: 'pending' })),
    intent: null,
    entities: [],
    queries: [],
    path: null,
    answer: '',
    result: null,
    error: null,
    totalMs: null,
  };
}

export function applyAskEvent(state: AskRunState, event: AskStreamEvent): AskRunState {
  switch (event.event) {
    case 'step': {
      const d = event.data;
      return {
        ...state,
        intent: d.intent ?? state.intent,
        entities: d.entities ?? state.entities,
        steps: state.steps.map((s) =>
          s.key === d.step
            ? { ...s, label: d.label || s.label, status: d.status, ms: d.ms ?? s.ms, detail: d.detail ?? s.detail }
            : s
        ),
      };
    }
    case 'query':
      return { ...state, queries: [...state.queries, event.data] };
    case 'path':
      return { ...state, path: event.data, intent: state.intent ?? event.data.intent };
    case 'token':
      return { ...state, answer: state.answer + event.data.text };
    case 'done': {
      const r = event.data;
      const traced = new Map((r.trace?.steps ?? []).map((s) => [s.step, s]));
      return {
        ...state,
        result: r,
        answer: r.answer,
        intent: r.intent ?? state.intent,
        entities: r.entities ?? state.entities,
        queries: r.trace?.queries ?? state.queries,
        totalMs: r.trace?.total_ms ?? null,
        steps: state.steps.map((s) => {
          const t = traced.get(s.key);
          return t ? { ...s, status: t.status, ms: t.ms, detail: t.detail ?? s.detail } : s;
        }),
      };
    }
    case 'error':
      return {
        ...state,
        error: event.data.message,
        steps: state.steps.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s)),
      };
    default:
      return state;
  }
}

const NOT_FOUND_TEXT = 'the answer is not found in the company brain.';

/** True once streamed text can no longer turn out to be the "not found" answer. */
export function answerIsSubstantive(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (t.length < 24) return false;
  if (NOT_FOUND_TEXT.startsWith(t) || t.includes('not found in the company brain')) return false;
  return !isNotFoundAnswer(text);
}

const STRUCTURED: AskIntent[] = ['impact', 'expertise', 'status'];

/**
 * Whether to show the evidence path yet. Impact, expertise and status results are computed from
 * the graph before the answer, so they show at once. A "why" path waits until the streamed answer
 * is clearly not "not found", so an unanswerable question never flashes an evidence path.
 */
export function showPathNow(state: AskRunState): boolean {
  if (state.result) return !isNotFoundAnswer(state.result.answer) && state.result.graph_path.nodes.length > 0;
  if (!state.path) return false;
  if (state.path.intent && STRUCTURED.includes(state.path.intent) && (state.path.sections.length || state.path.experts.length)) {
    return true;
  }
  return answerIsSubstantive(state.answer);
}

/** Sum of step times (what the steps took, excluding streaming overhead). */
export function stepsTotal(state: AskRunState): number {
  return state.steps.reduce((sum, s) => sum + (s.ms ?? 0), 0);
}

/** The decision node the answer is about: final once `done` arrives, provisional before. */
export function primaryNode(state: AskRunState | null) {
  if (!state || !showPathNow(state)) return undefined;
  const graph = state.result?.graph_path ?? state.path?.graph_path;
  const id = state.result ? state.result.primary_decision_id : state.path?.primary_decision_id;
  return id ? graph?.nodes.find((n) => n.id === id) : undefined;
}
