import { describe, it, expect } from 'vitest';
import { findDecisionDetail } from '../api/mocks';
import { buildLineageGraph } from '../utils/lineage';
import { splitDecisionCodes } from '../utils/links';

describe('lineage graph', () => {
  const keycloak = findDecisionDetail('Migrate session storage to embedded Keycloak cache')!;
  const kafka = findDecisionDetail('Adopt Kafka for all event messaging across services')!;

  it('includes the decision, its supersedes chain and its sources', () => {
    const g = buildLineageGraph(keycloak);
    const ids = g.nodes.map((n) => n.id);
    expect(ids[0]).toBe(`Decision:${keycloak.id}`);
    expect(ids).toContain(`Decision:${keycloak.lineage.supersedes[0].id}`);
    expect(ids).toContain('Ticket:TICK-102');
    expect(g.nodes.find((n) => n.isFocus)?.label).toMatch(/^DEC-\d{2} · /);
  });

  it('draws supersedes old -> new and sources -> decision (time flows left to right)', () => {
    const g = buildLineageGraph(keycloak);
    const old = `Decision:${keycloak.lineage.supersedes[0].id}`;
    const focus = `Decision:${keycloak.id}`;
    const edges = g.elements.edges.map((e) => e.data);
    expect(edges).toContainEqual(expect.objectContaining({ source: old, target: focus, type: 'supersedes' }));
    expect(edges).toContainEqual(expect.objectContaining({ source: 'Ticket:TICK-102', target: focus, type: 'based_on' }));
  });

  it('shows contradictions as contradicts edges', () => {
    const g = buildLineageGraph(kafka);
    expect(g.elements.edges.some((e) => e.data.type === 'contradicts')).toBe(true);
  });

  it('links decision nodes to their pages and respects the node cap', () => {
    const g = buildLineageGraph(keycloak, 2);
    expect(g.nodes).toHaveLength(2);
    expect(g.omitted).toBeGreaterThan(0);
    const decision = g.nodes.find((n) => n.type === 'Decision' && !n.isFocus)!;
    expect(decision.href).toMatch(/^\/decisions\/DEC-\d{2}$/);
  });
});

describe('splitDecisionCodes', () => {
  it('splits text around DEC codes', () => {
    expect(splitDecisionCodes('See DEC-11 and DEC-04.')).toEqual([
      { text: 'See ' },
      { text: 'DEC-11', code: 'DEC-11' },
      { text: ' and ' },
      { text: 'DEC-04', code: 'DEC-04' },
      { text: '.' },
    ]);
    expect(splitDecisionCodes('No codes')).toEqual([{ text: 'No codes' }]);
  });
});
