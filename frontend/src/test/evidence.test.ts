import { describe, it, expect } from 'vitest';
import { getMockAskResponse } from '../api/mocks';
import type { AskResponse } from '../api/types';
import { buildEvidencePath, pickMainDecision } from '../utils/evidence';

describe('evidence path', () => {
  const redis = getMockAskResponse('What replaced Redis for session storage?');

  it('prefers the decision whose title is quoted in the answer and that has a cited source', () => {
    const main = pickMainDecision(redis)!;
    expect(String(main.properties.title)).toMatch(/^Migrate session storage from Postgres to Redis cluster/);
  });

  it('demotes a superseded decision when status is known', () => {
    const node = (id: string, label: string, properties = {}) => ({ id, label, properties });
    const response: AskResponse = {
      answer: 'Both are described.',
      citations: [
        { type: 'ticket', id: 'TICK-1', title: 'A' },
        { type: 'ticket', id: 'TICK-2', title: 'B' },
      ],
      people: [],
      graph_path: {
        omitted_count: 0,
        nodes: [
          node('d_old', 'Decision', { title: 'Old thing' }),
          node('d_new', 'Decision', { title: 'New thing' }),
          node('t1', 'Ticket', { ticket_id: 'TICK-1' }),
          node('t2', 'Ticket', { ticket_id: 'TICK-2' }),
        ],
        edges: [
          { source: 'd_old', target: 't1', type: 'based_on', properties: {} },
          { source: 'd_new', target: 't2', type: 'based_on', properties: {} },
        ],
      },
    };
    expect(pickMainDecision(response)!.id).toBe('d_old');
    expect(pickMainDecision(response, new Map([['d_old', 'superseded' as const]]))!.id).toBe('d_new');
  });

  it('puts sources above the decision and related nodes below, only via real edges', () => {
    const main = pickMainDecision(redis)!;
    const path = buildEvidencePath(redis, main.id);
    const kinds = path.rows.map((r) => r.kind);
    const mainAt = path.rows.findIndex((r) => r.isMain);
    expect(path.rows.filter((r) => r.isMain)).toHaveLength(1);
    expect(kinds.slice(0, mainAt).every((k) => k === 'Ticket' || k === 'Meeting')).toBe(true);
    expect(kinds).toContain('System');

    const touching = new Set(
      redis.graph_path.edges
        .filter((e) => e.source === main.id || e.target === main.id)
        .flatMap((e) => [e.source, e.target])
    );
    for (const row of path.rows) expect(touching.has(row.nodeId)).toBe(true);
    expect(path.edgeCount).toBe(path.rows.length - 1);
  });

  it('labels supersedes and superseded-by relations from edge direction', () => {
    const node = (id: string, label: string, properties = {}) => ({ id, label, properties });
    const response: AskResponse = {
      answer: 'Keycloak replaced Redis.',
      citations: [{ type: 'ticket', id: 'TICK-1', title: 'T' }],
      people: [],
      graph_path: {
        omitted_count: 0,
        nodes: [
          node('d_new', 'Decision', { title: 'New' }),
          node('d_old', 'Decision', { title: 'Old' }),
          node('d_newer', 'Decision', { title: 'Newer' }),
          node('t1', 'Ticket', { ticket_id: 'TICK-1', title: 'T' }),
        ],
        edges: [
          { source: 'd_new', target: 'd_old', type: 'supersedes', properties: {} },
          { source: 'd_newer', target: 'd_new', type: 'supersedes', properties: {} },
          { source: 'd_new', target: 't1', type: 'based_on', properties: {} },
        ],
      },
    };
    const path = buildEvidencePath(response, 'd_new');
    expect(path.rows.map((r) => r.relation)).toEqual(['based on', null, 'supersedes', 'superseded by']);
    expect(path.rows[0].name).toBe('TICK-1');
  });

  it('has no cited decision for an unanswerable question', () => {
    const res = getMockAskResponse('Why did we choose quantum encryption for database backups?');
    expect(res.citations).toHaveLength(0);
  });
});
