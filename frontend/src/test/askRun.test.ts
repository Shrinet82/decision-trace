import { describe, expect, it } from 'vitest';
import streams from '../mocks/ask-stream.json';
import type { AskStreamEvent, DemoStatus } from '../api/types';
import { answerIsSubstantive, applyAskEvent, initialAskRun, primaryNode, showPathNow } from '../utils/askRun';
import { resetCountdownText } from '../utils/demo';
import { highlightAll } from '../utils/highlight';

const recorded = streams as unknown as Record<string, AskStreamEvent[]>;

function replay(question: string, until?: (e: AskStreamEvent) => boolean) {
  let state = initialAskRun();
  for (const e of recorded[question]) {
    state = applyAskEvent(state, e);
    if (until?.(e)) break;
  }
  return state;
}

describe('ask run reducer (recorded live streams)', () => {
  it('records every step with its time, the matched entities and each query', () => {
    const run = replay("What's affected if we drop Snowflake?");
    expect(run.steps.map((s) => s.status)).toEqual(['done', 'done', 'done', 'done', 'done']);
    expect(run.steps.every((s) => typeof s.ms === 'number')).toBe(true);
    expect(run.intent).toBe('impact');
    expect(run.entities).toEqual([{ label: 'System', name: 'Snowflake' }]);
    expect(run.queries.map((q) => q.name)).toEqual(
      expect.arrayContaining(['roster', 'impact_decisions', 'impact_people', 'impact_tickets'])
    );
    expect(run.totalMs).toBeGreaterThan(0);
    const decisions = run.result?.sections?.find((s) => s.key === 'decisions');
    expect(decisions?.items.map((i) => i.code)).toEqual(expect.arrayContaining(['DEC-03', 'DEC-13', 'DEC-17']));
  });

  it('shows structured results as soon as the path arrives, before any answer text', () => {
    const run = replay("What's affected if we drop Snowflake?", (e) => e.event === 'path');
    expect(run.answer).toBe('');
    expect(showPathNow(run)).toBe(true);
    expect(primaryNode(run)?.properties.decision_code).toBe('DEC-17');
  });

  it('never shows an evidence path for an unanswerable question, even mid-stream', () => {
    const q = 'Why did we choose quantum encryption for database backups?';
    let state = initialAskRun();
    for (const e of recorded[q]) {
      state = applyAskEvent(state, e);
      expect(showPathNow(state)).toBe(false);
    }
    expect(state.result?.graph_path.nodes).toEqual([]);
  });

  it('holds a "why" path until the streamed text cannot be the not-found answer', () => {
    expect(answerIsSubstantive('The answer is')).toBe(false);
    expect(answerIsSubstantive('The answer is not found in the Company Brain.')).toBe(false);
    expect(answerIsSubstantive('The decision to migrate session storage to Keycloak')).toBe(true);
    const run = replay('Why did we move sessions to Keycloak?');
    expect(primaryNode(run)?.properties.decision_code).toBe('DEC-11');
  });

  it('ranks Alice Vance first for Kafka expertise', () => {
    const run = replay('Who knows the most about Kafka?');
    expect(run.result?.experts?.[0].name).toBe('Alice Vance');
    expect(run.result?.primary_decision_id).toBeNull();
  });

  it('marks the running step as failed on an error event', () => {
    let s = applyAskEvent(initialAskRun(), {
      event: 'step',
      data: { step: 'understanding', status: 'running', label: 'Understanding the question' },
    });
    s = applyAskEvent(s, { event: 'error', data: { message: 'down' } });
    expect(s.error).toBe('down');
    expect(s.steps[0].status).toBe('error');
  });
});

describe('highlightAll', () => {
  it('highlights every quote found, ignoring case and whitespace, and skips missing ones', () => {
    const text = 'Alice decided: use Kafka.\nBob agreed to   migrate queues by Q1.';
    const segments = highlightAll(text, ['USE KAFKA', 'not in the text', 'migrate queues by Q1']);
    const marked = segments.filter((s) => s.quote !== undefined);
    expect(marked.map((s) => [s.text, s.quote])).toEqual([
      ['use Kafka', 0],
      ['migrate queues by Q1', 2],
    ]);
    expect(segments.map((s) => s.text).join('')).toBe(text);
  });
});

describe('resetCountdownText', () => {
  const base: DemoStatus = {
    has_demo_data: true,
    tagged_nodes: 2,
    tagged_edges: 7,
    last_ingest_at: '2026-10-17T12:00:00Z',
    resets_at: '2026-10-17T12:10:00Z',
    seconds_left: 600,
    auto_reset_minutes: 10,
  };
  it('counts down in whole minutes', () => {
    expect(resetCountdownText(base, Date.parse('2026-10-17T12:03:10Z'))).toBe('Demo data resets in 7 min');
    expect(resetCountdownText(base, Date.parse('2026-10-17T12:09:30Z'))).toBe('Demo data resets in 1 min');
    expect(resetCountdownText(base, Date.parse('2026-10-17T12:10:30Z'))).toBe('Demo data resets in under a minute');
  });
  it('explains the rule when there is no demo data', () => {
    expect(resetCountdownText({ ...base, has_demo_data: false, resets_at: null })).toMatch(/No demo data/);
    expect(resetCountdownText(undefined)).toMatch(/10 minutes after the last ingest/);
  });
});
