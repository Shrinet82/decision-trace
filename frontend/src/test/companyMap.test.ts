import { describe, expect, it } from 'vitest';
import type { GraphNode } from '../api/types';
import {
  DEFAULT_HIDDEN_TYPES,
  degreeMap,
  hiddenTypesFromParams,
  hideParamValue,
  MAX_NODE,
  MIN_NODE,
  nodeSize,
  searchNodes,
  seedPosition,
  toMapElements,
} from '../utils/companyMap';

const node = (id: string, label: string, props: Record<string, unknown> = {}): GraphNode =>
  ({ id, label, properties: props }) as unknown as GraphNode;

const nodes = [
  node('d1', 'Decision', { title: 'Adopt Kafka', decision_code: 'DEC-04' }),
  node('d2', 'Decision', { title: 'Adopt RabbitMQ', decision_code: 'DEC-07' }),
  node('s1', 'System', { name: 'Kafka' }),
  node('p1', 'Person', { name: 'Alice Vance' }),
  node('t1', 'Ticket', { ticket_id: 'TICK-105', title: 'Need event bus' }),
];
const edges = [
  { source: 'd1', target: 's1', type: 'about_system' },
  { source: 'd1', target: 'p1', type: 'decided_by' },
  { source: 'd2', target: 'd1', type: 'contradicts' },
  { source: 'd1', target: 't1', type: 'based_on' },
] as never[];

describe('company map helpers', () => {
  it('sizes nodes by degree on a bounded square-root scale', () => {
    expect(nodeSize(0, 10)).toBe(MIN_NODE);
    expect(nodeSize(10, 10)).toBe(MAX_NODE);
    expect(nodeSize(1, 10)).toBeGreaterThan(nodeSize(0, 10));
    expect(nodeSize(4, 10)).toBeGreaterThan(nodeSize(2, 10));
    expect(nodeSize(3, 0)).toBeGreaterThanOrEqual(MIN_NODE);
  });

  it('counts each edge for both ends', () => {
    const degree = degreeMap({ nodes, edges });
    expect(degree.get('d1')).toBe(4);
    expect(degree.get('s1')).toBe(1);
  });

  it('starts every layout from the same positions', () => {
    const types = ['Decision', 'Person', 'System'];
    expect(seedPosition('d1', 'Decision', types)).toEqual(seedPosition('d1', 'Decision', types));
    expect(seedPosition('d1', 'Decision', types)).not.toEqual(seedPosition('d2', 'Decision', types));
  });

  it('builds elements with colour, size, status and the decision code as the label', () => {
    const els = toMapElements({ nodes, edges }, new Map([['d1', 'conflict' as const]]));
    const d1 = els.nodes?.find((n) => n.data.id === 'd1');
    expect(d1?.data).toMatchObject({ label: 'DEC-04', type: 'Decision', status: 'conflict', color: '#4F5BD5' });
    expect(els.nodes?.find((n) => n.data.id === 'p1')?.data.status).toBe('active');
    expect(els.edges).toHaveLength(4);
    const ids = els.edges?.map((e) => e.data.id);
    expect(new Set(ids).size).toBe(ids?.length);
  });

  it('searches by title, code and ticket id, prefix matches first', () => {
    expect(searchNodes(nodes, 'k').length).toBe(0);
    expect(searchNodes(nodes, 'kafka').map((n) => n.id)).toEqual(['s1', 'd1']);
    expect(searchNodes(nodes, 'DEC-07').map((n) => n.id)).toEqual(['d2']);
    expect(searchNodes(nodes, 'tick-105').map((n) => n.id)).toEqual(['t1']);
  });

  it('hides tickets on the map by default, nothing in focus view, and remembers "show all"', () => {
    expect([...hiddenTypesFromParams(new URLSearchParams(''))]).toEqual([...DEFAULT_HIDDEN_TYPES]);
    expect(hiddenTypesFromParams(new URLSearchParams('node=d1')).size).toBe(0);
    expect([...hiddenTypesFromParams(new URLSearchParams('hide=Person,Team'))]).toEqual(['Person', 'Team']);
    expect(hiddenTypesFromParams(new URLSearchParams('hide=none')).size).toBe(0);
    expect(hideParamValue(new Set())).toBe('none');
    expect(hideParamValue(new Set(['Ticket']))).toBe('Ticket');
  });
});
