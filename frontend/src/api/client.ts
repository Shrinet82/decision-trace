import { parseSse, toAskEvent, toIngestEvent, type SseMessage } from './sse';
import type {
  Attention,
  AskRequest,
  AskResponse,
  AskStreamEvent,
  DemoStatus,
  SourceDocument,
  SourceKind,
  SourceList,
  ChangeEntry,
  DecisionDetail,
  DecisionSummary,
  GraphResponse,
  IngestEvent,
  IngestRequest,
  PersonDetail,
  PersonSummary,
  ResetResult,
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

/* ------------------------------------------------------------------------------------------ */
/* Live ingest                                                                                 */
/* ------------------------------------------------------------------------------------------ */

function detailText(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  // FastAPI validation errors: [{ loc: [...], msg: '...' }]
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { loc?: unknown[]; msg?: unknown };
    const field = Array.isArray(first.loc) ? first.loc.filter((p) => p !== 'body').join('.') : '';
    if (typeof first.msg === 'string') return field ? `${field}: ${first.msg}` : first.msg;
  }
  return null;
}

/** A readable message for a failed ingest or reset request. */
export function ingestErrorMessage(status: number, body: unknown): string {
  const detail = detailText(body);
  switch (status) {
    case 429:
      return 'Too many ingests from this address. You can run 3 per minute; wait a moment and try again.';
    case 409:
      return 'Another ingest is already running. Wait for it to finish, then try again.';
    case 422:
      return `The source was rejected${detail ? `: ${detail}` : '. Check the title, date and text.'}`;
    default:
      return detail
        ? `Ingest failed (${status}): ${detail}`
        : `Ingest failed: the server responded with ${status}.`;
  }
}

function abortError(): Error {
  const error = new Error('The ingest was cancelled.');
  error.name = 'AbortError';
  return error;
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** Delay between simulated events in mock mode: long enough to see each step running. */
export const MOCK_EVENT_INTERVAL_MS = 350;

/**
 * POST /ingest and stream its server-sent events to `onEvent` as they arrive. EventSource cannot
 * POST, so this reads the body with a stream reader and parses it with `parseSse`. Resolves when
 * the stream ends after a `diff` or `error` event; rejects with an ApiError for a non-2xx response
 * or a stream that ends early, and with an AbortError when `signal` is aborted.
 */
export async function streamIngest(
  request: IngestRequest,
  onEvent: (event: IngestEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  if (USE_MOCKS) {
    const { getMockIngestEvents, recordMockIngest } = await loadMocks();
    for (const event of getMockIngestEvents(request.text)) {
      await wait(MOCK_EVENT_INTERVAL_MS, signal);
      if (event.event === 'diff') recordMockIngest(request, event.data);
      onEvent(event);
    }
    return;
  }

  const response = await fetch(`${API_BASE_URL}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(ingestErrorMessage(response.status, body), response.status, body);
  }
  if (!response.body) {
    throw new ApiError('The server returned an empty ingest stream.', response.status);
  }

  let finished = false;
  await readSse(response.body, (message) => {
    const event = toIngestEvent(message);
    if (!event) return;
    if (event.event === 'diff' || event.event === 'error') finished = true;
    onEvent(event);
  });

  if (!finished) {
    throw new ApiError('The ingest stream ended before a result arrived. Try again.', 0);
  }
}

/** Reads a server-sent-events body to the end, calling `onMessage` for each complete event. */
async function readSse(body: ReadableStream<Uint8Array>, onMessage: (m: SseMessage) => void): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let rest = '';
  const dispatch = (text: string) => {
    const parsed = parseSse(text);
    rest = parsed.rest;
    parsed.events.forEach(onMessage);
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      dispatch(rest + decoder.decode(value, { stream: true }));
    }
    // Flush a final event that was not followed by a blank line
    dispatch(`${rest}${decoder.decode()}\n\n`);
  } finally {
    reader.releaseLock();
  }
}

/* ------------------------------------------------------------------------------------------ */
/* Streamed Ask                                                                                */
/* ------------------------------------------------------------------------------------------ */

/** Mock playback runs each recorded step at this fraction of its real duration (capped). */
const INSTANT = import.meta.env.MODE === 'test';
export const MOCK_STEP_SCALE = INSTANT ? 0 : 0.35;
export const MOCK_STEP_MAX_MS = 900;
export const MOCK_TOKEN_INTERVAL_MS = INSTANT ? 0 : 40;

/**
 * POST /ask/stream and hand each event to `onEvent` as it arrives. Resolves after `done` or
 * `error`; rejects with an ApiError for a non-2xx response or a stream that ends early. In mock
 * mode it replays a stream recorded from the live API, waiting each step's recorded time.
 */
export async function streamAsk(
  question: string,
  onEvent: (event: AskStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  if (USE_MOCKS) {
    const { getMockAskStream } = await loadMocks();
    for (const event of await getMockAskStream(question)) {
      if (event.event === 'step' && event.data.status !== 'running') {
        await wait(Math.min((event.data.ms ?? 0) * MOCK_STEP_SCALE, MOCK_STEP_MAX_MS), signal);
      } else if (event.event === 'token') {
        await wait(MOCK_TOKEN_INTERVAL_MS, signal);
      }
      onEvent(event);
    }
    return;
  }

  const response = await fetch(`${API_BASE_URL}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      response.status === 429
        ? 'Too many questions from this address. Wait a minute and try again.'
        : `Search failed: the server responded with ${response.status}.`;
    throw new ApiError(message, response.status, body);
  }
  if (!response.body) throw new ApiError('The server returned an empty answer stream.', response.status);

  let finished = false;
  await readSse(response.body, (message) => {
    const event = toAskEvent(message);
    if (!event) return;
    if (event.event === 'done' || event.event === 'error') finished = true;
    onEvent(event);
  });
  if (!finished) throw new ApiError('The answer stream ended before a result arrived. Try again.', 0);
}

/* ------------------------------------------------------------------------------------------ */
/* Sources and demo status                                                                     */
/* ------------------------------------------------------------------------------------------ */

export async function listSources(): Promise<SourceList> {
  if (USE_MOCKS) return (await loadMocks()).getMockSources();
  return getJson<SourceList>('/sources', 'Failed to load sources');
}

export async function getSource(kind: SourceKind, key: string): Promise<SourceDocument> {
  if (USE_MOCKS) {
    const mock = await (await loadMocks()).getMockSource(kind, key);
    if (!mock) throw new ApiError(`Source ${key} not found`, 404);
    return mock;
  }
  return getJson<SourceDocument>(
    `/sources/${kind}/${encodeURIComponent(key)}`,
    `Failed to load ${key}`
  );
}

/** GET /ingest/status: whether demo data is present and when it resets automatically. */
export async function getDemoStatus(): Promise<DemoStatus> {
  if (USE_MOCKS) return (await loadMocks()).getMockDemoStatus();
  return getJson<DemoStatus>('/ingest/status', 'Failed to load demo status');
}

/** POST /ingest/reset: removes everything added by demo ingests. */
export async function resetIngest(): Promise<ResetResult> {
  if (USE_MOCKS) {
    await wait(300);
    return (await loadMocks()).resetMockIngest();
  }
  const response = await fetch(`${API_BASE_URL}/ingest/reset`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      response.status === 409
        ? 'An ingest is running. Wait for it to finish, then reset.'
        : response.status === 429
          ? 'Too many requests. Wait a moment and try again.'
          : `Reset failed: the server responded with ${response.status}.`;
    throw new ApiError(message, response.status, body);
  }
  return response.json();
}

/** GET /changes, newest first. */
export async function listChanges(limit = 20): Promise<ChangeEntry[]> {
  if (USE_MOCKS) return (await loadMocks()).listMockChanges(limit);
  return getJson<ChangeEntry[]>(`/changes?limit=${limit}`, 'Failed to load changes');
}

/** GET /attention: conflicts, orphaned systems, stale and superseded-but-active decisions. */
export async function getAttention(): Promise<Attention> {
  if (USE_MOCKS) return (await loadMocks()).getMockAttention();
  return getJson<Attention>('/attention', 'Failed to load the attention queue');
}
