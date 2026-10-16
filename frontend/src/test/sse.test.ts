import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseSse, toIngestEvent, type SseMessage } from '../api/sse';
import type { IngestEvent } from '../api/types';

/** Feeds chunks through the parser the way the stream reader does. */
function feed(chunks: string[]): { events: SseMessage[]; rest: string } {
  let rest = '';
  const events: SseMessage[] = [];
  for (const chunk of chunks) {
    const parsed = parseSse(rest + chunk);
    events.push(...parsed.events);
    rest = parsed.rest;
  }
  return { events, rest };
}

const STEP = 'event: step\ndata: {"step":"reading","status":"running","label":"Reading source"}\n\n';
const DIFF = 'event: diff\ndata: {"summary":"1 new decision"}\n\n';

describe('parseSse', () => {
  it('parses a single complete event', () => {
    const { events, rest } = parseSse(STEP);
    expect(events).toEqual([
      { event: 'step', data: '{"step":"reading","status":"running","label":"Reading source"}' },
    ]);
    expect(rest).toBe('');
  });

  it('parses several events in one chunk', () => {
    const { events } = parseSse(STEP + DIFF + STEP);
    expect(events.map((e) => e.event)).toEqual(['step', 'diff', 'step']);
  });

  it('keeps an event split mid-line until it is complete', () => {
    const whole = STEP + DIFF;
    for (let cut = 1; cut < whole.length; cut += 1) {
      const { events, rest } = feed([whole.slice(0, cut), whole.slice(cut)]);
      expect(events.map((e) => e.event)).toEqual(['step', 'diff']);
      expect(rest).toBe('');
    }
  });

  it('handles one character per chunk', () => {
    const { events } = feed([...(STEP + DIFF)]);
    expect(events).toHaveLength(2);
    expect(JSON.parse(events[0].data).label).toBe('Reading source');
  });

  it('handles CRLF line endings, including a CR and LF split across chunks', () => {
    const crlf = (STEP + DIFF).replace(/\n/g, '\r\n');
    for (let cut = 1; cut < crlf.length; cut += 1) {
      const { events, rest } = feed([crlf.slice(0, cut), crlf.slice(cut)]);
      expect(events.map((e) => e.event)).toEqual(['step', 'diff']);
      expect(rest).toBe('');
    }
  });

  it('handles bare CR line endings (a trailing CR waits for the next chunk)', () => {
    const cr = STEP.replace(/\n/g, '\r');
    expect(parseSse(cr).events).toHaveLength(0);
    const { events, rest } = parseSse(`${cr}event: step`);
    expect(events).toHaveLength(1);
    expect(rest).toBe('event: step');
  });

  it('ignores comments and joins multi-line data', () => {
    const { events } = parseSse(': keep-alive\n\nevent: error\ndata: {"message":\ndata: "boom"}\n\n');
    expect(events).toEqual([{ event: 'error', data: '{"message":\n"boom"}' }]);
  });

  it('defaults the event name to message and accepts fields without a space', () => {
    const { events } = parseSse('data:{"a":1}\n\n');
    expect(events).toEqual([{ event: 'message', data: '{"a":1}' }]);
  });

  it('returns the unterminated tail as rest', () => {
    const { events, rest } = parseSse(`${STEP}event: diff\ndata: {"summ`);
    expect(events).toHaveLength(1);
    expect(rest).toBe('event: diff\ndata: {"summ');
  });
});

describe('toIngestEvent', () => {
  it('decodes known events and skips unknown names or bad JSON', () => {
    expect(toIngestEvent({ event: 'diff', data: '{"summary":"x"}' })).toEqual({
      event: 'diff',
      data: { summary: 'x' },
    });
    expect(toIngestEvent({ event: 'ping', data: '{}' })).toBeNull();
    expect(toIngestEvent({ event: 'step', data: '{not json' })).toBeNull();
  });
});

describe('streamIngest over fetch', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  async function loadLiveClient() {
    vi.stubEnv('VITE_USE_MOCKS', 'false');
    vi.resetModules();
    return import('../api/client');
  }

  function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    return new ReadableStream({
      start(controller) {
        for (const c of chunks) controller.enqueue(encoder.encode(c));
        controller.close();
      },
    });
  }

  it('emits events across awkward chunk boundaries and posts the request', async () => {
    const body = (STEP + DIFF).replace(/\n/g, '\r\n');
    const fetchMock = vi.fn(async () =>
      new Response(streamOf([body.slice(0, 7), body.slice(7, 61), body.slice(61)]), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    const { streamIngest } = await loadLiveClient();

    const seen: IngestEvent[] = [];
    await streamIngest(
      { type: 'meeting', title: 'Sync', date: '2026-10-16', text: 'Kafka' },
      (e) => seen.push(e)
    );
    expect(seen.map((e) => e.event)).toEqual(['step', 'diff']);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/ingest$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({ type: 'meeting', text: 'Kafka' });
  });

  it('flushes a final event that is not followed by a blank line', async () => {
    vi.stubGlobal('fetch', async () =>
      new Response(streamOf([STEP, 'event: diff\ndata: {"summary":"x"}']), { status: 200 })
    );
    const { streamIngest } = await loadLiveClient();
    const seen: string[] = [];
    await streamIngest({ type: 'meeting', title: 't', date: '2026-10-16', text: 'x' }, (e) => seen.push(e.event));
    expect(seen).toEqual(['step', 'diff']);
  });

  it('rejects when the stream ends without a diff or error', async () => {
    vi.stubGlobal('fetch', async () => new Response(streamOf([STEP]), { status: 200 }));
    const { streamIngest } = await loadLiveClient();
    await expect(
      streamIngest({ type: 'meeting', title: 't', date: '2026-10-16', text: 'x' }, () => undefined)
    ).rejects.toThrow(/ended before a result/);
  });

  it.each([
    [429, /3 per minute/],
    [409, /Another ingest is already running/],
    [422, /rejected: text: String should have at most 5000 characters/],
  ])('maps HTTP %i to a friendly ApiError', async (status, message) => {
    const detail =
      status === 422
        ? [{ loc: ['body', 'text'], msg: 'String should have at most 5000 characters' }]
        : 'nope';
    vi.stubGlobal('fetch', async () =>
      new Response(JSON.stringify({ detail }), { status, headers: { 'Content-Type': 'application/json' } })
    );
    const { streamIngest, ApiError } = await loadLiveClient();
    const promise = streamIngest({ type: 'meeting', title: 't', date: '2026-10-16', text: 'x' }, () => undefined);
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({ status });
    await expect(promise).rejects.toThrow(message);
  });
});
