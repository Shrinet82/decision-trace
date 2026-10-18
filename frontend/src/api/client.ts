import { parseSse, toAskEvent, toBatchEvent, toGithubEvent, toIngestEvent, type SseMessage } from './sse';
import type {
  Attention,
  AskRequest,
  AskResponse,
  AskStreamEvent,
  BatchEvent,
  BatchFilePayload,
  GithubEvent,
  DemoStatus,
  SourceDocument,
  SourceKind,
  SourceList,
  ChangeEntry,
  DecisionDetail,
  DecisionSummary,
  GraphResponse,
  IngestDiff,
  IngestEvent,
  IngestRequest,
  OrgInfo,
  PersonDetail,
  PersonSummary,
  ResetResult,
  SystemDetail,
  SystemSummary,
} from './types';
import { apiOrgPrefix, getCurrentOrg } from '../org/orgState';
// Fixtures are loaded on demand so they stay out of the production bundle.
const loadMocks = () => import('./mocks');

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '/api' : 'http://localhost:8000');

/** API base for the current organization: `/orgs/<id>` is added for every organization but the sample. */
function apiBase(): string {
  return `${API_BASE_URL}${apiOrgPrefix()}`;
}

export const USE_MOCKS =
  import.meta.env.VITE_USE_MOCKS !== undefined
    ? import.meta.env.VITE_USE_MOCKS === 'true' || import.meta.env.VITE_USE_MOCKS === '1'
    : typeof window !== 'undefined' &&
      (window.location.port === '4173' ||
        window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1');

/** In mock mode every organization but the sample is a new, empty one. */
function mockEmptyOrg(): boolean {
  return USE_MOCKS && getCurrentOrg() !== null;
}

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


/* ------------------------------------------------------------------------------------------ */
/* Requests: timeouts and readable errors                                                       */
/* ------------------------------------------------------------------------------------------ */

/** Plain requests give up after this long; streams get this long to start and between chunks. */
export const REQUEST_TIMEOUT_MS = 25_000;
export const STREAM_IDLE_MS = 60_000;
export const NETWORK_MESSAGE = "Can't reach the server. Check your connection, then try again.";
export const TIMEOUT_MESSAGE = 'The server took too long to respond. Try again in a moment.';

/** What the user sees for a failed request: what went wrong and what to do about it. */
export function httpErrorMessage(status: number, body: unknown, subject: string): string {
  const detail = detailText(body);
  if (status === 429) return detail ?? 'Too many requests from this address. Wait a minute and try again.';
  if (status === 404) return `${subject} was not found.`;
  if (status === 504 || status === 408) return TIMEOUT_MESSAGE;
  if (status === 502) return 'The API is unreachable right now. Try again in a moment.';
  if (status >= 500) return 'The server ran into a problem. Try again in a moment.';
  return detail ?? `${subject} could not be loaded (the server responded with ${status}).`;
}

/**
 * fetch with a timeout and readable failures: an unreachable server is an ApiError with status 0
 * and a timeout one with status 408. The caller's own signal still cancels the request.
 */
async function apiFetch(url: string, init: RequestInit = {}, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const outer = init.signal ?? undefined;
  const onAbort = () => controller.abort();
  if (outer?.aborted) controller.abort();
  else outer?.addEventListener('abort', onAbort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new ApiError(TIMEOUT_MESSAGE, 408);
    if ((error as { name?: string } | null)?.name === 'AbortError') throw error;
    throw new ApiError(NETWORK_MESSAGE, 0);
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener('abort', onAbort);
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

  const response = await apiFetch(`${apiBase()}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(httpErrorMessage(response.status, errorBody, 'The answer'), response.status, errorBody);
  }

  return response.json();
}

/**
 * Fetch a full decision page by DEC code (DEC-11), id, or exact title.
 */
export async function getDecision(decisionId: string): Promise<DecisionDetail> {
  if (mockEmptyOrg()) throw new ApiError('Not found', 404);
  if (USE_MOCKS) {
    const { findDecisionDetail } = await loadMocks();
    const mock = findDecisionDetail(decisionId);
    if (!mock) throw new ApiError(`Decision ${decisionId} not found`, 404);
    return mock;
  }

  const response = await apiFetch(`${apiBase()}/decisions/${encodeURIComponent(decisionId)}`, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(
      httpErrorMessage(response.status, errorBody, `Decision ${decisionId}`),
      response.status,
      errorBody
    );
  }

  return response.json();
}

async function getJson<T>(path: string, failure: string): Promise<T> {
  const response = await apiFetch(`${apiBase()}${path}`, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(httpErrorMessage(response.status, errorBody, failure), response.status, errorBody);
  }

  return response.json();
}

/**
 * Fetch all decisions with computed health.
 */
export async function listDecisions(): Promise<DecisionSummary[]> {
  if (mockEmptyOrg()) return [];
  if (USE_MOCKS) return (await loadMocks()).MOCK_DECISIONS;
  return getJson<DecisionSummary[]>('/decisions?limit=500', 'Failed to load decisions');
}

/**
 * Fetch the full graph (the API caps a response at 500 nodes).
 */
export async function getGraph(): Promise<GraphResponse> {
  if (mockEmptyOrg()) return { nodes: [], edges: [], total_nodes: 0, total_edges: 0 } as unknown as GraphResponse;
  if (USE_MOCKS) return (await loadMocks()).MOCK_GRAPH;
  return getJson<GraphResponse>('/graph?limit=500', 'Failed to load graph');
}

export async function listSystems(): Promise<SystemSummary[]> {
  if (mockEmptyOrg()) return [];
  if (USE_MOCKS) return (await loadMocks()).MOCK_SYSTEMS;
  return getJson<SystemSummary[]>('/systems', 'Failed to load systems');
}

export async function getSystem(name: string): Promise<SystemDetail> {
  if (mockEmptyOrg()) throw new ApiError('Not found', 404);
  if (USE_MOCKS) {
    const { MOCK_SYSTEM_DETAILS, findByName } = await loadMocks();
    const mock = findByName(MOCK_SYSTEM_DETAILS, name);
    if (!mock) throw new ApiError(`System ${name} not found`, 404);
    return mock;
  }
  return getJson<SystemDetail>(`/systems/${encodeURIComponent(name)}`, `Failed to load system ${name}`);
}

export async function listPeople(): Promise<PersonSummary[]> {
  if (mockEmptyOrg()) return [];
  if (USE_MOCKS) return (await loadMocks()).MOCK_PEOPLE;
  return getJson<PersonSummary[]>('/people', 'Failed to load people');
}

export async function getPerson(name: string): Promise<PersonDetail> {
  if (mockEmptyOrg()) throw new ApiError('Not found', 404);
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
      return detail && /demo limit/i.test(detail)
        ? detail
        : 'Too many ingests from this address. You can run 3 per minute; wait a moment and try again.';
    case 409:
      return 'Another ingest is already running. Wait for it to finish, then try again.';
    case 422:
      return `The source was rejected${detail ? `: ${detail}` : '. Check the title, date and text.'}`;
    default:
      if (status >= 500) return 'The server ran into a problem while reading the source. Try again in a moment.';
      return detail ? `Ingest failed (${status}): ${detail}` : `Ingest failed: the server responded with ${status}.`;
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

  const response = await apiFetch(`${apiBase()}/ingest`, {
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
      let stall: ReturnType<typeof setTimeout> | undefined;
      const stalled = new Promise<never>((_, reject) => {
        stall = setTimeout(() => reject(new ApiError(TIMEOUT_MESSAGE, 408)), STREAM_IDLE_MS);
      });
      const { done, value } = await Promise.race([reader.read(), stalled]).finally(() => clearTimeout(stall));
      if (done) break;
      dispatch(rest + decoder.decode(value, { stream: true }));
    }
    // Flush a final event that was not followed by a blank line
    dispatch(`${rest}${decoder.decode()}\n\n`);
  } finally {
    // A stalled stream is cancelled so the connection is released
    reader.cancel().catch(() => undefined);
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

  const response = await apiFetch(`${apiBase()}/ask/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(httpErrorMessage(response.status, body, 'The answer'), response.status, body);
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
  if (mockEmptyOrg()) return { items: [], counts: {} };
  if (USE_MOCKS) return (await loadMocks()).getMockSources();
  return getJson<SourceList>('/sources', 'Failed to load sources');
}

export async function getSource(kind: SourceKind, key: string): Promise<SourceDocument> {
  if (mockEmptyOrg()) throw new ApiError('Not found', 404);
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
  if (mockEmptyOrg()) return { has_demo_data: false, tagged_nodes: 0, tagged_edges: 0, last_ingest_at: null, resets_at: null, seconds_left: null, auto_reset_minutes: null };
  if (USE_MOCKS) return (await loadMocks()).getMockDemoStatus();
  return getJson<DemoStatus>('/ingest/status', 'Failed to load demo status');
}

/** POST /ingest/reset: removes everything added by demo ingests. */
export async function resetIngest(): Promise<ResetResult> {
  if (USE_MOCKS) {
    await wait(300);
    return (await loadMocks()).resetMockIngest();
  }
  const response = await apiFetch(`${apiBase()}/ingest/reset`, {
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
  if (mockEmptyOrg()) return [];
  if (USE_MOCKS) return (await loadMocks()).listMockChanges(limit);
  return getJson<ChangeEntry[]>(`/changes?limit=${limit}`, 'Failed to load changes');
}

/** GET /attention: conflicts, orphaned systems, stale and superseded-but-active decisions. */
export async function getAttention(): Promise<Attention> {
  if (mockEmptyOrg()) return { conflicts: [], orphaned_systems: [], stale: [], superseded_active: [] } as unknown as Attention;
  if (USE_MOCKS) return (await loadMocks()).getMockAttention();
  return getJson<Attention>('/attention', 'Failed to load the attention queue');
}

/* ------------------------------------------------------------------------------------------ */
/* Organizations                                                                               */
/* ------------------------------------------------------------------------------------------ */

const SAMPLE_ORG: OrgInfo = { id: 'sample', name: 'Acme Corp (sample)', sample: true, created_at: null };

/** POST /orgs: a new, empty organization with its own graph. */
export async function createOrg(name: string): Promise<OrgInfo> {
  if (USE_MOCKS) {
    await wait(120);
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'org';
    return { id: `${slug}-3f9a1c`, name, sample: false, created_at: new Date().toISOString() };
  }
  const response = await apiFetch(`${API_BASE_URL}/orgs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(httpErrorMessage(response.status, body, 'The organization'), response.status, body);
  }
  return response.json();
}

/** GET /orgs/{id}: the organization, or a 404 ApiError if it was deleted or expired. */
export async function getOrg(id: string): Promise<OrgInfo> {
  if (id === 'sample') return SAMPLE_ORG;
  if (USE_MOCKS) return { id, name: id.replace(/-[0-9a-f]{6}$/, '').replace(/-/g, ' '), sample: false, created_at: null, nodes: 0, edges: 0, idle_hours_before_deletion: 72 };
  const response = await apiFetch(`${API_BASE_URL}/orgs/${encodeURIComponent(id)}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(httpErrorMessage(response.status, body, 'The organization'), response.status, body);
  }
  return response.json();
}

/** DELETE /orgs/{id}: removes the organization and its graph. */
export async function deleteOrg(id: string): Promise<void> {
  if (USE_MOCKS) {
    await wait(120);
    return;
  }
  const response = await apiFetch(`${API_BASE_URL}/orgs/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok && response.status !== 404) {
    const body = await response.json().catch(() => null);
    throw new ApiError(httpErrorMessage(response.status, body, 'The organization'), response.status, body);
  }
}

/* ------------------------------------------------------------------------------------------ */
/* File upload                                                                                 */
/* ------------------------------------------------------------------------------------------ */

/**
 * POST /ingest/batch: ingest uploaded files and stream per-file progress, ending with one combined
 * `diff` (or an `error` when no file could be ingested). Resolves when the stream ends.
 */
export async function streamBatch(
  files: BatchFilePayload[],
  onEvent: (event: BatchEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  if (USE_MOCKS) {
    const { getMockIngestEvents, recordMockIngest } = await loadMocks();
    onEvent({
      event: 'files',
      data: {
        files: files.map((f, index) => ({
          index,
          name: f.name,
          type: f.type === 'auto' ? 'adr' : f.type,
          title: f.name.replace(/\.[A-Za-z0-9]+$/, ''),
          chars: f.text?.length ?? 0,
          rejected: f.name.toLowerCase().includes('scan') ? 'The PDF has no extractable text (it looks like a scan).' : null,
        })),
      },
    });
    let last: IngestDiff | null = null;
    for (const [index, f] of files.entries()) {
      if (f.name.toLowerCase().includes('scan')) {
        onEvent({ event: 'file', data: { index, name: f.name, status: 'skipped', message: 'The PDF has no extractable text (it looks like a scan).' } });
        continue;
      }
      onEvent({ event: 'file', data: { index, name: f.name, status: 'running' } });
      for (const event of getMockIngestEvents(f.text ?? 'kafka')) {
        await wait(MOCK_EVENT_INTERVAL_MS / 2, signal);
        if (event.event === 'step' || event.event === 'graph') onEvent({ event: event.event, data: { ...event.data, file: index } } as BatchEvent);
        if (event.event === 'diff') last = event.data;
      }
      if (last) onEvent({ event: 'file', data: { index, name: f.name, status: 'done', summary: last.summary } });
    }
    if (last) {
      recordMockIngest({ type: 'announcement', title: `${files.length} files`, date: '2026-10-18', text: '' }, last);
      onEvent({ event: 'diff', data: last });
    } else {
      onEvent({ event: 'error', data: { message: 'No file could be ingested. See the messages for each file.' } });
    }
    return;
  }

  const response = await apiFetch(`${apiBase()}/ingest/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ files }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(ingestErrorMessage(response.status, body), response.status, body);
  }
  if (!response.body) throw new ApiError('The server returned an empty ingest stream.', response.status);
  let finished = false;
  await readSse(response.body, (message) => {
    const event = toBatchEvent(message);
    if (!event) return;
    if (event.event === 'diff' || event.event === 'error') finished = true;
    onEvent(event);
  });
  if (!finished) throw new ApiError('The ingest stream ended before a result arrived. Try again.', 0);
}

/* ------------------------------------------------------------------------------------------ */
/* GitHub import                                                                               */
/* ------------------------------------------------------------------------------------------ */

/** Messages for a failed GitHub import request (the stream itself reports its own errors). */
export function githubErrorMessage(status: number, body: unknown): string {
  const detail = detailText(body);
  if (status === 403) return detail ?? 'GitHub import is only available in organizations you create.';
  if (status === 422) return 'That does not look like a repository URL. Use https://github.com/owner/repo.';
  return ingestErrorMessage(status, body);
}

/**
 * POST /ingest/github: import ADRs (and optionally decision-like PRs and issues) from a public
 * repository. Streams `progress` events and ends with a `diff` or `error`.
 */
export async function streamGithub(
  repoUrl: string,
  includePrs: boolean,
  onEvent: (event: GithubEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  if (USE_MOCKS) {
    const { getMockIngestEvents } = await loadMocks();
    const phases: [GithubEvent & { event: 'progress' }][] = [
      [{ event: 'progress', data: { phase: 'fetching', status: 'running', label: 'Fetching repository', detail: 'owner/repo' } }],
      [{ event: 'progress', data: { phase: 'fetching', status: 'done', label: 'Fetching repository', detail: 'found 12 ADRs and 3 decision-like PRs/issues' } }],
      [{ event: 'progress', data: { phase: 'extracting', status: 'done', label: 'Extracting systems and decisions', detail: '12 ADR decisions, 2 of 3 PRs/issues recorded a decision' } }],
      [{ event: 'progress', data: { phase: 'linking', status: 'done', label: 'Linking decisions', detail: '2 supersedes links' } }],
      [{ event: 'progress', data: { phase: 'writing', status: 'done', label: 'Writing to FalkorDB', detail: '61 nodes, 89 edges' } }],
    ];
    if (/nope|missing/i.test(repoUrl)) {
      await wait(MOCK_EVENT_INTERVAL_MS, signal);
      onEvent({ event: 'error', data: { message: 'That repository was not found. It must be public, and the URL spelled correctly.' } });
      return;
    }
    for (const [event] of phases) {
      await wait(MOCK_EVENT_INTERVAL_MS, signal);
      onEvent(event);
    }
    const diff = getMockIngestEvents('kafka').find((e) => e.event === 'diff');
    if (diff && diff.event === 'diff') {
      onEvent({
        event: 'diff',
        data: { ...diff.data, import: { repo: 'owner/repo', adrs: 12, items_considered: 3, items_decisions: includePrs ? 2 : 0, supersedes: 2, tokens_estimated: 12566, seconds: 36.9 } },
      });
    }
    return;
  }

  const response = await apiFetch(`${apiBase()}/ingest/github`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ repo_url: repoUrl, include_prs: includePrs }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(githubErrorMessage(response.status, body), response.status, body);
  }
  if (!response.body) throw new ApiError('The server returned an empty import stream.', response.status);
  let finished = false;
  await readSse(response.body, (message) => {
    const event = toGithubEvent(message);
    if (!event) return;
    if (event.event === 'diff' || event.event === 'error') finished = true;
    onEvent(event);
  });
  if (!finished) throw new ApiError('The import stream ended before a result arrived. Try again.', 0);
}
