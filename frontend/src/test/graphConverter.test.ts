import { describe, it, expect } from 'vitest';
import { convertGraphPathToCytoscape } from '../utils/graphConverter';
import type { GraphPath, Citation } from '../api/types';

describe('Cytoscape Graph Converter', () => {
  it('handles empty or undefined graph path gracefully', () => {
    const emptyRes = convertGraphPathToCytoscape(undefined);
    expect(emptyRes.elements.nodes).toHaveLength(0);
    expect(emptyRes.elements.edges).toHaveLength(0);
    expect(emptyRes.nodeCount).toBe(0);
    expect(emptyRes.omittedCount).toBe(0);
  });

  it('converts nodes and assigns correct shapes and line colors', () => {
    const samplePath: GraphPath = {
      nodes: [
        {
          id: 'dec_1',
          label: 'Decision',
          properties: {
            title: 'Adopt Kafka for messaging',
            status: 'accepted',
            system: 'Kafka',
          },
        },
        {
          id: 'Alice',
          label: 'Person',
          properties: { name: 'Alice' },
        },
        {
          id: 'Kafka',
          label: 'System',
          properties: { name: 'Kafka' },
        },
        {
          id: 'TICK-101',
          label: 'Ticket',
          properties: { ticket_id: 'TICK-101', title: 'Latency issue' },
        },
      ],
      edges: [
        {
          source: 'dec_1',
          target: 'Kafka',
          type: 'about_system',
        },
      ],
      omitted_count: 5,
    };

    const citations: Citation[] = [
      { id: 'TICK-101', title: 'Latency issue', type: 'ticket' },
    ];

    const result = convertGraphPathToCytoscape(samplePath, citations, false);

    expect(result.nodeCount).toBe(4);
    expect(result.edgeCount).toBe(1);
    expect(result.omittedCount).toBe(5);

    const decNode = result.elements.nodes.find((n) => n.data.id === 'dec_1');
    expect(decNode?.data.nodeType).toBe('decision');
    expect(decNode?.data.lineColor).toBe('#C72C7A'); // Messaging light color

    const ticketNode = result.elements.nodes.find((n) => n.data.id === 'TICK-101');
    expect(ticketNode?.data.nodeType).toBe('ticket');
    expect(ticketNode?.data.isCited).toBe(true);
  });

  it('labels supersedes edge as replaces and contradicts edge as conflicts with', () => {
    const pathWithEdges: GraphPath = {
      nodes: [
        { id: 'dec_new', label: 'Decision', properties: { title: 'New DB' } },
        { id: 'dec_old', label: 'Decision', properties: { title: 'Old DB' } },
        { id: 'dec_alt', label: 'Decision', properties: { title: 'Alt DB' } },
      ],
      edges: [
        {
          source: 'dec_new',
          target: 'dec_old',
          type: 'supersedes',
        },
        {
          source: 'dec_new',
          target: 'dec_alt',
          type: 'contradicts',
        },
      ],
      omitted_count: 0,
    };

    const result = convertGraphPathToCytoscape(pathWithEdges, [], false);
    const supersedesEdge = result.elements.edges.find((e) => e.data.type === 'supersedes');
    expect(supersedesEdge?.data.label).toBe('replaces');
    expect(supersedesEdge?.data.edgeStyle).toBe('solid');

    const contradictsEdge = result.elements.edges.find((e) => e.data.type === 'contradicts');
    expect(contradictsEdge?.data.label).toBe('conflicts with');
    expect(contradictsEdge?.data.edgeStyle).toBe('dashed');
    expect(contradictsEdge?.data.edgeColor).toBe('#C62828');
  });

  it('uses darker variants when isDark is true', () => {
    const path: GraphPath = {
      nodes: [
        {
          id: 'dec_1',
          label: 'Decision',
          properties: { title: 'Vault adoption', system: 'Vault' },
        },
      ],
      edges: [],
      omitted_count: 0,
    };

    const resultDark = convertGraphPathToCytoscape(path, [], true);
    const node = resultDark.elements.nodes[0];
    expect(node.data.lineColor).toBe('#1BB5AC'); // Identity dark color
  });
});
