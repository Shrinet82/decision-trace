import ask1 from '../mocks/ask-1-rabbitmq-kafka.json';
import ask2 from '../mocks/ask-2-elasticsearch-owner.json';
import ask3 from '../mocks/ask-3-redis-replacement.json';
import ask4 from '../mocks/ask-4-prometheus-decider.json';
import ask5 from '../mocks/ask-5-vault-secrets.json';
import ask6 from '../mocks/ask-6-unanswerable-quantum.json';
import ask7 from '../mocks/ask-7-unanswerable-oracle.json';
import decisionsFixture from '../mocks/decisions.json';
import decisionDetailsFixture from '../mocks/decision-details.json';
import graphFixture from '../mocks/graph.json';
import systemsFixture from '../mocks/systems.json';
import systemDetailsFixture from '../mocks/system-details.json';
import peopleFixture from '../mocks/people.json';
import personDetailsFixture from '../mocks/person-details.json';
import ingestKafkaFixture from '../mocks/ingest-kafka.json';
import ingestAliceFixture from '../mocks/ingest-alice-leaves.json';
import type {
  AskResponse,
  ChangeEntry,
  DecisionDetail,
  DecisionSummary,
  GraphResponse,
  IngestDiff,
  IngestEvent,
  IngestRequest,
  PersonDetail,
  PersonSummary,
  ResetResult,
  SystemDetail,
  SystemSummary,
} from './types';

export const MOCK_DECISIONS = decisionsFixture as unknown as DecisionSummary[];
export const MOCK_DECISION_DETAILS = decisionDetailsFixture as unknown as Record<
  string,
  DecisionDetail
>;
export const MOCK_GRAPH = graphFixture as unknown as GraphResponse;
export const MOCK_SYSTEMS = systemsFixture as unknown as SystemSummary[];
export const MOCK_SYSTEM_DETAILS = systemDetailsFixture as unknown as Record<string, SystemDetail>;
export const MOCK_PEOPLE = peopleFixture as unknown as PersonSummary[];
export const MOCK_PERSON_DETAILS = personDetailsFixture as unknown as Record<string, PersonDetail>;

/** Case-insensitive lookup in a fixture keyed by name. */
export function findByName<T>(fixture: Record<string, T>, name: string): T | undefined {
  const key = Object.keys(fixture).find((k) => k.toLowerCase() === name.toLowerCase());
  return key ? fixture[key] : undefined;
}

/** A decision page by DEC code, id, or exact title. */
export function findDecisionDetail(ref: string): DecisionDetail | undefined {
  const all = Object.values(MOCK_DECISION_DETAILS);
  const upper = ref.toUpperCase();
  return all.find((d) => d.id === ref || d.decision_code?.toUpperCase() === upper || d.title === ref);
}

export interface BenchmarkQuestion {
  id: string;
  question: string;
  response: AskResponse;
}

export const BENCHMARK_QUESTIONS: BenchmarkQuestion[] = [
  {
    id: 'ask-1',
    question: 'Why did we choose Kafka over RabbitMQ?',
    response: ask1 as AskResponse,
  },
  {
    id: 'ask-2',
    question: 'Who owns Elasticsearch?',
    response: ask2 as AskResponse,
  },
  {
    id: 'ask-3',
    question: 'What replaced Redis for session storage?',
    response: ask3 as AskResponse,
  },
  {
    id: 'ask-4',
    question: 'Who decided to adopt Prometheus?',
    response: ask4 as AskResponse,
  },
  {
    id: 'ask-5',
    question: 'Why did we choose Vault for secret management?',
    response: ask5 as AskResponse,
  },
  {
    id: 'ask-6',
    question: 'Why did we choose quantum encryption for database backups?',
    response: ask6 as AskResponse,
  },
  {
    id: 'ask-7',
    question: 'What replaced Oracle DB for payment transactions?',
    response: ask7 as AskResponse,
  },
];

/**
 * Returns a mock AskResponse based on matching keywords in the prompt.
 */
export function getMockAskResponse(question: string): AskResponse {
  const q = question.toLowerCase();

  if (q.includes('redis') || q.includes('session storage')) {
    return ask3 as AskResponse;
  }
  if (q.includes('prometheus') || q.includes('metrics')) {
    return ask4 as AskResponse;
  }
  if (q.includes('vault') || q.includes('secret')) {
    return ask5 as AskResponse;
  }
  if (q.includes('rabbitmq') || q.includes('kafka')) {
    return ask1 as AskResponse;
  }
  if (q.includes('elasticsearch')) {
    return ask2 as AskResponse;
  }
  if (q.includes('quantum')) {
    return ask6 as AskResponse;
  }
  if (q.includes('oracle')) {
    return ask7 as AskResponse;
  }

  // Fallback default: question not found
  return {
    answer: 'The answer is not found in the Company Brain.',
    citations: [],
    people: [],
    primary_decision_id: null,
    graph_path: {
      nodes: [],
      edges: [],
      omitted_count: 0,
    },
  };
}

/* Live ingest -------------------------------------------------------------------------------- */

export const MOCK_INGEST_KAFKA = ingestKafkaFixture as unknown as IngestEvent[];
export const MOCK_INGEST_ALICE = ingestAliceFixture as unknown as IngestEvent[];

/** Recorded event stream for a source text: "Kafka" or a departure, else the Kafka stream. */
export function getMockIngestEvents(text: string): IngestEvent[] {
  const t = text.toLowerCase();
  if (t.includes('kafka')) return MOCK_INGEST_KAFKA;
  if (t.includes('leaves') || t.includes('left the company')) return MOCK_INGEST_ALICE;
  return MOCK_INGEST_KAFKA;
}

// In-memory change log so the mock app behaves like the API within one page session.
let mockChanges: ChangeEntry[] = [];
let mockIngestedNodes = 0;
let mockIngestedEdges = 0;

export function recordMockIngest(request: IngestRequest, diff: IngestDiff): void {
  mockIngestedNodes += diff.nodes_added.length;
  mockIngestedEdges += diff.edges_added.length;
  mockChanges = [
    {
      id: diff.ingest_id,
      kind: 'ingest',
      title: request.title,
      type: request.type,
      created_at: new Date().toISOString(),
      summary: diff.summary,
      diff,
    },
    ...mockChanges,
  ];
}

export function resetMockIngest(): ResetResult {
  const restored = mockChanges
    .filter((c) => c.kind === 'ingest')
    .reduce(
      (sum, c) =>
        sum +
        (c.diff ? c.diff.status_changes.length + c.diff.person_changes.length + c.diff.orphan_changes.length : 0),
      0
    );
  const result: ResetResult = {
    removed_nodes: mockIngestedNodes,
    removed_edges: mockIngestedEdges,
    restored_properties: restored,
    nodes: MOCK_GRAPH.total_nodes,
    edges: MOCK_GRAPH.total_edges,
  };
  mockIngestedNodes = 0;
  mockIngestedEdges = 0;
  mockChanges = [
    {
      id: `reset_${Date.now()}`,
      kind: 'reset',
      title: 'Demo data reset',
      created_at: new Date().toISOString(),
      summary: `Removed ${result.removed_nodes} nodes and ${result.removed_edges} edges`,
    },
    ...mockChanges,
  ];
  return result;
}

export function listMockChanges(limit: number): ChangeEntry[] {
  return mockChanges.slice(0, limit);
}
