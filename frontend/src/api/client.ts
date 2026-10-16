import type {
  AskRequest,
  AskResponse,
  DecisionDetail,
  DecisionSummary,
  GraphResponse,
  PersonDetail,
  PersonSummary,
  SystemDetail,
  SystemSummary,
} from './types';
// Fixtures are loaded on demand so they stay out of the production bundle.
const loadMocks = () => import('./mocks');

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '/api' : 'http://localhost:8000');

export const USE_MOCKS =
  import.meta.env.VITE_USE_MOCKS !== undefined
    ? import.meta.env.VITE_USE_MOCKS === 'true' || import.meta.env.VITE_USE_MOCKS === '1'
    : typeof window !== 'undefined' &&
      (window.location.port === '4173' ||
        window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1');

export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

/**
 * Ask a natural language question about decisions and evidence paths.
 */
export async function askQuestion(payload: AskRequest): Promise<AskResponse> {
  if (USE_MOCKS) {
    // Simulate brief network latency for realism
    await new Promise((resolve) => setTimeout(resolve, 80));
    const { getMockAskResponse } = await loadMocks();
    return getMockAskResponse(payload.question);
  }

  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(
      `Failed to get answer: ${response.statusText} (${response.status})`,
      response.status,
      errorBody
    );
  }

  return response.json();
}

/**
 * Fetch a full decision page by DEC code (DEC-11), id, or exact title.
 */
export async function getDecision(decisionId: string): Promise<DecisionDetail> {
  if (USE_MOCKS) {
    const { findDecisionDetail } = await loadMocks();
    const mock = findDecisionDetail(decisionId);
    if (!mock) throw new ApiError(`Decision ${decisionId} not found`, 404);
    return mock;
  }

  const response = await fetch(`${API_BASE_URL}/decisions/${encodeURIComponent(decisionId)}`, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(
      `Failed to load decision ${decisionId}: ${response.statusText} (${response.status})`,
      response.status,
      errorBody
    );
  }

  return response.json();
}

async function getJson<T>(path: string, failure: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(
      `${failure}: ${response.statusText} (${response.status})`,
      response.status,
      errorBody
    );
  }

  return response.json();
}

/**
 * Fetch all decisions with computed health.
 */
export async function listDecisions(): Promise<DecisionSummary[]> {
  if (USE_MOCKS) return (await loadMocks()).MOCK_DECISIONS;
  return getJson<DecisionSummary[]>('/decisions?limit=500', 'Failed to load decisions');
}

/**
 * Fetch the full graph (the API caps a response at 500 nodes).
 */
export async function getGraph(): Promise<GraphResponse> {
  if (USE_MOCKS) return (await loadMocks()).MOCK_GRAPH;
  return getJson<GraphResponse>('/graph?limit=500', 'Failed to load graph');
}

export async function listSystems(): Promise<SystemSummary[]> {
  if (USE_MOCKS) return (await loadMocks()).MOCK_SYSTEMS;
  return getJson<SystemSummary[]>('/systems', 'Failed to load systems');
}

export async function getSystem(name: string): Promise<SystemDetail> {
  if (USE_MOCKS) {
    const { MOCK_SYSTEM_DETAILS, findByName } = await loadMocks();
    const mock = findByName(MOCK_SYSTEM_DETAILS, name);
    if (!mock) throw new ApiError(`System ${name} not found`, 404);
    return mock;
  }
  return getJson<SystemDetail>(`/systems/${encodeURIComponent(name)}`, `Failed to load system ${name}`);
}

export async function listPeople(): Promise<PersonSummary[]> {
  if (USE_MOCKS) return (await loadMocks()).MOCK_PEOPLE;
  return getJson<PersonSummary[]>('/people', 'Failed to load people');
}

export async function getPerson(name: string): Promise<PersonDetail> {
  if (USE_MOCKS) {
    const { MOCK_PERSON_DETAILS, findByName } = await loadMocks();
    const mock = findByName(MOCK_PERSON_DETAILS, name);
    if (!mock) throw new ApiError(`Person ${name} not found`, 404);
    return mock;
  }
  return getJson<PersonDetail>(`/people/${encodeURIComponent(name)}`, `Failed to load ${name}`);
}
