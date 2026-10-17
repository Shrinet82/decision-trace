import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { streamAsk } from '../api/client';
import { applyAskEvent, initialAskRun, type AskRunState } from '../utils/askRun';

/**
 * One streamed run per question, shared by every component that shows it (the turn, the
 * "How I found this" panel, the properties panel). A question is streamed once; later readers get
 * the stored state, like a query cache.
 */
const runs = new Map<string, AskRunState>();
const listeners = new Set<() => void>();
const controllers = new Map<string, AbortController>();

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function startAskRun(question: string, force = false): void {
  if (!force && runs.has(question)) return;
  controllers.get(question)?.abort();
  const controller = new AbortController();
  controllers.set(question, controller);
  runs.set(question, initialAskRun());
  emit();

  const update = (fn: (s: AskRunState) => AskRunState) => {
    if (controller.signal.aborted) return;
    runs.set(question, fn(runs.get(question) ?? initialAskRun()));
    emit();
  };

  streamAsk(question, (event) => update((s) => applyAskEvent(s, event)), controller.signal).catch(
    (err: unknown) => {
      if (err instanceof Error && err.name === 'AbortError') return;
      const message = err instanceof Error ? err.message : 'The Company Brain could not answer right now.';
      update((s) => applyAskEvent(s, { event: 'error', data: { message } }));
    }
  );
}

/** Test helper: forget every run. */
export function clearAskRuns(): void {
  controllers.forEach((c) => c.abort());
  controllers.clear();
  runs.clear();
  emit();
}

/** The run for `question` (started on first use), and a retry that streams it again. */
export function useAskRun(question: string | null): { run: AskRunState | null; retry: () => void } {
  const run = useSyncExternalStore(
    subscribe,
    () => (question ? runs.get(question) ?? null : null),
    () => null
  );
  useEffect(() => {
    if (question) startAskRun(question);
  }, [question]);
  const retry = useCallback(() => {
    if (question) startAskRun(question, true);
  }, [question]);
  return { run, retry };
}
