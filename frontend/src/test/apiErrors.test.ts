import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/** The client against a failing server (mock mode off): every failure reads as a clear message. */
async function loadClient() {
  vi.resetModules();
  vi.stubEnv('VITE_USE_MOCKS', 'false');
  return import('../api/client');
}

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('failed requests', () => {
  it('an unreachable server says so and has status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const { listDecisions, NETWORK_MESSAGE } = await loadClient();
    await expect(listDecisions()).rejects.toMatchObject({ status: 0, message: NETWORK_MESSAGE });
  });

  it('a 5xx is a plain "ran into a problem", never the raw status text', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(503, { detail: 'boom' })));
    const { listSystems } = await loadClient();
    const error = await listSystems().catch((e) => e);
    expect(error.status).toBe(503);
    expect(error.message).toBe('The server ran into a problem. Try again in a moment.');
  });

  it('a gateway failure from the edge proxy reads as unreachable or slow', async () => {
    const { httpErrorMessage, TIMEOUT_MESSAGE } = await loadClient();
    expect(httpErrorMessage(502, null, 'x')).toBe('The API is unreachable right now. Try again in a moment.');
    expect(httpErrorMessage(504, null, 'x')).toBe(TIMEOUT_MESSAGE);
  });

  it('a 429 passes the server text on, including the demo limit message', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(429, { detail: 'Demo limit reached: try tomorrow.' })));
    const { listPeople } = await loadClient();
    await expect(listPeople()).rejects.toMatchObject({ status: 429, message: 'Demo limit reached: try tomorrow.' });
  });

  it('an unknown decision is a 404 with its code in the message', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(404, { detail: 'nope' })));
    const { getDecision } = await loadClient();
    await expect(getDecision('DEC-99')).rejects.toMatchObject({ status: 404, message: 'Decision DEC-99 was not found.' });
  });

  it('a request that never answers times out after 25 s', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        })
      )
    );
    const { listDecisions, TIMEOUT_MESSAGE, REQUEST_TIMEOUT_MS } = await loadClient();
    const pending = listDecisions().catch((e) => e);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 10);
    expect(await pending).toMatchObject({ status: 408, message: TIMEOUT_MESSAGE });
  });

  it('a caller abort stays an AbortError, not a timeout', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        })
      )
    );
    const { streamAsk } = await loadClient();
    const controller = new AbortController();
    const pending = streamAsk('why?', () => undefined, controller.signal).catch((e) => e);
    controller.abort();
    expect((await pending).name).toBe('AbortError');
  });
});

describe('ingest and ask failures', () => {
  it('ingest 429 and 409 tell the user what to do', async () => {
    const { ingestErrorMessage } = await loadClient();
    expect(ingestErrorMessage(429, { detail: 'Ingest rate limit: at most 3 per minute.' })).toContain('3 per minute');
    expect(ingestErrorMessage(409, null)).toContain('Wait for it to finish');
    expect(ingestErrorMessage(429, { detail: 'Demo limit reached: used up.' })).toBe('Demo limit reached: used up.');
    expect(ingestErrorMessage(502, null)).toContain('Try again in a moment');
  });

  it('a 429 on Ask names the limit', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json(429, { detail: 'Rate limit exceeded: maximum 20 requests per minute per IP.' })));
    const { streamAsk } = await loadClient();
    await expect(streamAsk('q', () => undefined)).rejects.toMatchObject({ status: 429, message: expect.stringContaining('20 requests per minute') });
  });
});
