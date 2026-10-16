import { describe, it, expect } from 'vitest';
import { getMockAskResponse } from '../api/mocks';
import type { AskResponse } from '../api/types';
import { buildEvidencePath } from '../utils/evidence';

describe('evidence path', () => {
  const redis = getMockAskResponse('What replaced Redis for session storage?');

  it('uses the server-chosen primary decision for the evidence path', () => {
    const mainId = redis.primary_decision_id!;
    expect(mainId).toBeTruthy();
    const path = buildEvidencePath(redis, mainId);
    expect(path.rows.filter((r) => r.isMain)).toHaveLength(1);
    expect(path.rows.find((r) => r.isMain)!.nodeId).toBe(mainId);
    expect(path.rows.find((r) => r.isMain)!.code).toMatch(/^DEC-\d{2}$/);
  });

  it('puts sources above the decision and related nodes below, only via real edges', () => {
    const main = { id: redis.primary_decision_id! };
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
      primary_decision_id: 'd_new',
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

  it('has no primary decision or citations for an unanswerable question', () => {
    const res = getMockAskResponse('Why did we choose quantum encryption for database backups?');
    expect(res.citations).toHaveLength(0);
    expect(res.primary_decision_id).toBeNull();
  });
});
