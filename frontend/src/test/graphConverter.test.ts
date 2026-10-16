import { describe, it, expect } from 'vitest';
import { buildCypher, neighborhood, toCytoscapeElements } from '../utils/graphConverter';
import { index, rows } from './fixtures';

describe('graph neighborhood', () => {
  const kafka = rows.find((r) => r.title.startsWith('Adopt Kafka'))!;

  it('returns only the focus node at 0 reach and grows with hops', () => {
    const one = neighborhood(index, kafka.id, 1, new Set());
    const two = neighborhood(index, kafka.id, 2, new Set());
    expect(one.nodes.some((n) => n.id === kafka.id)).toBe(true);
    expect(two.nodes.length).toBeGreaterThan(one.nodes.length);
    for (const e of one.edges) {
      const ids = new Set(one.nodes.map((n) => n.id));
      expect(ids.has(e.source) && ids.has(e.target)).toBe(true);
    }
  });

  it('returns the whole graph for "all"', () => {
    const all = neighborhood(index, kafka.id, 'all', new Set());
    expect(all.nodes).toHaveLength(index.nodes.length);
    expect(all.edges).toHaveLength(index.edges.length);
  });

  it('hides node types but always keeps the focus node', () => {
    const hidden = neighborhood(index, kafka.id, 2, new Set(['Ticket', 'Person', 'Decision']));
    expect(hidden.nodes.some((n) => n.label === 'Ticket')).toBe(false);
    expect(hidden.nodes.some((n) => n.label === 'Person')).toBe(false);
    expect(hidden.nodes.some((n) => n.id === kafka.id)).toBe(true);
  });

  it('builds a Cypher query for the focus node', () => {
    const focus = index.byId.get(kafka.id)!;
    expect(buildCypher(focus, 2)).toBe(
      `MATCH p = (n:Decision {id: '${kafka.id}'})-[*1..2]-() RETURN p`
    );
    expect(buildCypher(focus, 'all')).toContain('-[*]-');
  });
});

describe('cytoscape elements', () => {
  it('creates one element per visible node and edge, with status and an icon', () => {
    const kafka = rows.find((r) => r.title.startsWith('Adopt Kafka'))!;
    const visible = neighborhood(index, kafka.id, 1, new Set());
    const statusById = new Map(rows.map((r) => [r.id, r.status]));
    const els = toCytoscapeElements(visible, statusById);
    expect(els.nodes).toHaveLength(visible.nodes.length);
    expect(els.edges).toHaveLength(visible.edges.length);
    const focusEl = els.nodes!.find((n) => n.data.id === kafka.id)!;
    expect(focusEl.data.status).toBe('conflict');
    expect(String(focusEl.data.icon)).toMatch(/^data:image\/svg\+xml/);
    expect(els.edges!.some((e) => e.data.type === 'contradicts')).toBe(true);
  });
});
