import ask1 from '../mocks/ask-1-rabbitmq-kafka.json';
import ask2 from '../mocks/ask-2-elasticsearch-owner.json';
import ask3 from '../mocks/ask-3-redis-replacement.json';
import ask4 from '../mocks/ask-4-prometheus-decider.json';
import ask5 from '../mocks/ask-5-vault-secrets.json';
import ask6 from '../mocks/ask-6-unanswerable-quantum.json';
import ask7 from '../mocks/ask-7-unanswerable-oracle.json';
import type { AskResponse } from './types';

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
    graph_path: {
      nodes: [],
      edges: [],
      omitted_count: 0,
    },
  };
}
