import { describe, expect, it } from 'vitest';
import { getMockIngestEvents, MOCK_INGEST_ALICE, MOCK_INGEST_KAFKA } from '../api/mocks';
import { INGEST_STEPS, type ChangeEntry, type IngestDiff, type IngestEvent } from '../api/types';
import { PRESETS, toIngestRequest } from '../components/ingest/ingestForm';
import {
  isDecisionChanged,
  isPersonChanged,
  isSystemChanged,
  recentDiff,
  RECENT_CHANGE_MS,
} from '../utils/changes';
import { findQuote } from '../utils/highlight';
import { applyIngestEvent, initialRun, mergeGraph, miniGraphElements } from '../utils/ingestRun';

const diffOf = (events: IngestEvent[]): IngestDiff => {
  const last = events[events.length - 1];
  if (last.event !== 'diff') throw new Error('fixture must end with a diff');
  return last.data;
};

describe('mock ingest fixtures', () => {
  it.each([
    ['kafka', MOCK_INGEST_KAFKA],
    ['alice', MOCK_INGEST_ALICE],
  ])('%s: steps run in contract order and the stream ends with a diff', (_name, events) => {
    const order = events.filter((e) => e.event === 'step').map((e) => (e.event === 'step' ? e.data.step : ''));
    const firstSeen = order.filter((s, i) => order.indexOf(s) === i);
    expect(firstSeen).toEqual([...INGEST_STEPS]);
    expect(events[events.length - 1].event).toBe('diff');
  });

  it('chooses the fixture by text', () => {
    expect(getMockIngestEvents(PRESETS[0].form.text)).toBe(MOCK_INGEST_KAFKA);
    expect(getMockIngestEvents(PRESETS[1].form.text)).toBe(MOCK_INGEST_ALICE);
    expect(getMockIngestEvents('Bob leaves the team')).toBe(MOCK_INGEST_ALICE);
    expect(getMockIngestEvents('anything else')).toBe(MOCK_INGEST_KAFKA);
  });
});

describe('run state', () => {
  it('moves steps through running and done, and records the diff', () => {
    let state = initialRun();
    expect(state.steps.every((s) => s.status === 'pending')).toBe(true);
    state = applyIngestEvent(state, {
      event: 'step',
      data: { step: 'reading', status: 'running', label: 'Reading the meeting' },
    });
    expect(state.steps[0]).toMatchObject({ status: 'running', label: 'Reading the meeting' });
    state = applyIngestEvent(state, {
      event: 'step',
      data: { step: 'reading', status: 'done', label: 'Reading the meeting', detail: '289 characters' },
    });
    expect(state.steps[0]).toMatchObject({ status: 'done', detail: '289 characters' });

    for (const e of MOCK_INGEST_KAFKA) state = applyIngestEvent(state, e);
    expect(state.steps.every((s) => s.status === 'done')).toBe(true);
    expect(state.diff?.summary).toMatch(/1 new decision/);
  });

  it('marks the running step as failed on an error event', () => {
    let state = applyIngestEvent(initialRun(), {
      event: 'step',
      data: { step: 'matching', status: 'running', label: 'Matching' },
    });
    state = applyIngestEvent(state, { event: 'error', data: { message: 'LLM timed out' } });
    expect(state.steps.find((s) => s.key === 'matching')?.status).toBe('error');
    expect(state.error?.message).toBe('LLM timed out');
  });

  it('accumulates graph events without downgrading added nodes or edges', () => {
    const merged = mergeGraph(
      {
        nodes: [{ id: 'Decision:a', label: 'Decision', name: 'A', change: 'added' }],
        edges: [{ source: 'Decision:a', target: 'System:Kafka', type: 'about_system', change: 'added' }],
      },
      {
        nodes: [
          { id: 'Decision:a', label: 'Decision', name: 'A', decision_code: 'DEC-18', change: 'context' },
          { id: 'System:Kafka', label: 'System', name: 'Kafka', change: 'context' },
        ],
        edges: [{ source: 'Decision:a', target: 'System:Kafka', type: 'about_system', change: 'context' }],
      }
    );
    expect(merged.nodes).toHaveLength(2);
    expect(merged.nodes[0]).toMatchObject({ change: 'added', decision_code: 'DEC-18' });
    expect(merged.edges).toEqual([
      { source: 'Decision:a', target: 'System:Kafka', type: 'about_system', change: 'added' },
    ]);
  });

  it('drops edges whose endpoints are not in the mini graph', () => {
    const elements = miniGraphElements({
      nodes: [{ id: 'Meeting:Sync', label: 'Meeting', name: 'Sync', change: 'added' }],
      edges: [{ source: 'Meeting:Sync', target: 'Person:Nobody', type: 'attended_by', change: 'added' }],
    });
    expect(elements.nodes).toHaveLength(1);
    expect(elements.edges).toHaveLength(0);
    expect(elements.nodes[0].data).toMatchObject({ change: 'added', type: 'Meeting' });
  });
});

describe('change markers', () => {
  const kafka = diffOf(MOCK_INGEST_KAFKA);
  const alice = diffOf(MOCK_INGEST_ALICE);

  it('marks new decisions and status changes', () => {
    expect(isDecisionChanged(kafka, 'DEC-18')).toBe(true);
    expect(isDecisionChanged(kafka, 'dec-07')).toBe(true);
    expect(isDecisionChanged(kafka, 'DEC-04')).toBe(true);
    expect(isDecisionChanged(kafka, 'DEC-11')).toBe(false);
    expect(isDecisionChanged(null, 'DEC-18')).toBe(false);
  });

  it('marks systems that a new decision is about, or whose ownership changed', () => {
    expect(isSystemChanged(kafka, 'Kafka')).toBe(true);
    expect(isSystemChanged(kafka, 'RabbitMQ')).toBe(false);
    expect(isSystemChanged(alice, 'Redis')).toBe(true);
    expect(isSystemChanged(alice, 'Vault')).toBe(false);
  });

  it('marks people whose record changed', () => {
    expect(isPersonChanged(alice, 'Alice Vance')).toBe(true);
    expect(isPersonChanged(kafka, 'Alice Vance')).toBe(false);
  });

  it('seeds the latest diff only from a recent ingest', () => {
    const now = Date.parse('2026-10-17T12:00:00Z');
    const entry: ChangeEntry = {
      id: 'x',
      kind: 'ingest',
      title: 'Architecture sync',
      created_at: new Date(now - 5 * 60 * 1000).toISOString(),
      summary: kafka.summary,
      diff: kafka,
    };
    expect(recentDiff(entry, now)).toBe(kafka);
    expect(recentDiff({ ...entry, created_at: new Date(now - RECENT_CHANGE_MS - 1000).toISOString() }, now)).toBeNull();
    expect(recentDiff({ ...entry, kind: 'reset' }, now)).toBeNull();
    expect(recentDiff({ ...entry, reverted: true }, now)).toBeNull();
    expect(recentDiff(undefined, now)).toBeNull();
  });
});

describe('findQuote', () => {
  const text = 'Context first.\nAlice Vance decided: Migrate session\nstorage to embedded Keycloak cache. Done.';

  it('matches case-insensitively and across line wraps', () => {
    const m = findQuote(text, 'alice vance decided: migrate session storage to embedded keycloak cache.');
    expect(m?.before).toBe('Context first.\n');
    expect(m?.match).toBe('Alice Vance decided: Migrate session\nstorage to embedded Keycloak cache.');
    expect(m?.after).toBe(' Done.');
  });

  it('tolerates surrounding quotation marks', () => {
    expect(findQuote(text, '“Migrate session storage to embedded Keycloak cache”')?.match).toBe(
      'Migrate session\nstorage to embedded Keycloak cache'
    );
  });

  it('returns null when the quote is absent or empty', () => {
    expect(findQuote(text, 'Adopt Kafka')).toBeNull();
    expect(findQuote(text, null)).toBeNull();
  });
});

describe('ingest form', () => {
  it('builds the request from a preset, splitting participants', () => {
    expect(toIngestRequest(PRESETS[0].form)).toEqual({
      type: 'meeting',
      title: 'Architecture sync',
      date: '2026-10-16',
      text: PRESETS[0].form.text,
      participants: ['Alice Vance', 'Bob Martin', 'Kevin Flynn'],
    });
    expect(toIngestRequest(PRESETS[1].form)).not.toHaveProperty('participants');
  });
});
