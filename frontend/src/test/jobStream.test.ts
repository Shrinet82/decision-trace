import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/** An import is a server-side job: a dropped stream re-attaches instead of failing. */
async function loadClient() {
  vi.stubEnv('VITE_USE_MOCKS', 'false');
  vi.resetModules();
  return import('../api/client');
}

const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const sse = (chunks: string[], fail = false) => {
  const encoder = new TextEncoder();
  let sent = false;
  return new Response(
    new ReadableStream({
      pull(controller) {
        if (!sent) {
          sent = true;
          for (const c of chunks) controller.enqueue(encoder.encode(c));
          if (!fail) controller.close();
        } else {
          controller.error(new TypeError('network error'));
        }
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
  );
};
const progress = (detail: string) => ({ phase: 'extracting', status: 'running', label: 'Extracting', detail });
const diff = { summary: '17 new decisions', import: { repo: 'o/r' } };

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('GitHub import survives a dropped stream', () => {
  it('re-attaches from the number of events already seen and reports the result', async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      calls.push(String(url));
      if (String(url).endsWith('/ingest/github')) {
        // job event + one progress event, then the connection breaks (the 60 s stall in real life)
        return sse([frame('job', { id: 'job_aaaaaaaaaaaa', kind: 'github' }), frame('progress', progress('1/40'))], true);
      }
      return sse([frame('progress', progress('40/40')), frame('diff', diff)]);
    });
    vi.stubGlobal('fetch', fetchMock);
    const { streamGithub } = await loadClient();
    const seen: string[] = [];
    let jobId = '';
    const done = streamGithub('https://github.com/o/r', true, (e) => seen.push(`${e.event}:${e.event === 'progress' ? e.data.detail : ''}`), undefined, (id) => (jobId = id));
    await vi.advanceTimersByTimeAsync(2000);
    await done;
    expect(seen).toEqual(['progress:1/40', 'progress:40/40', 'diff:']);
    expect(jobId).toBe('job_aaaaaaaaaaaa');
    // the second request asks for events after the two it already had (job + one progress)
    expect(calls[1]).toMatch(/\/jobs\/job_aaaaaaaaaaaa\/stream\?from=2$/);
  });

  it('keeps reconnecting while the job runs, but stops at once when the job is gone', async () => {
    let n = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).endsWith('/ingest/github')) return sse([frame('job', { id: 'job_bbbbbbbbbbbb', kind: 'github' })], true);
        n += 1;
        return new Response('{"detail":"gone"}', { status: 404, headers: { 'Content-Type': 'application/json' } });
      })
    );
    const { streamGithub } = await loadClient();
    const failure = streamGithub('https://github.com/o/r', true, () => undefined).catch((e) => e);
    await vi.advanceTimersByTimeAsync(5000);
    const error = await failure;
    expect(error.status).toBe(404);
    expect(error.message).toMatch(/no longer tracked/);
    expect(n).toBe(1);
  });

  it('a stream that ends with an error event is a result, not a reconnect', async () => {
    const fetchMock = vi.fn(async () =>
      sse([frame('job', { id: 'job_cccccccccccc', kind: 'github' }), frame('error', { message: 'That repository was not found.' })])
    );
    vi.stubGlobal('fetch', fetchMock);
    const { streamGithub } = await loadClient();
    const seen: string[] = [];
    await streamGithub('https://github.com/o/nope', true, (e) => seen.push(e.event === 'error' ? e.data.message : e.event));
    expect(seen).toEqual(['That repository was not found.']);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('a reloaded page resumes the running job', () => {
  it('replays the latest job from its first event', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        calls.push(String(url));
        if (String(url).includes('/jobs/latest')) {
          return new Response(JSON.stringify({ id: 'job_dddddddddddd', kind: 'github', status: 'running', finished_at: null }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return sse([frame('job', { id: 'job_dddddddddddd', kind: 'github' }), frame('progress', progress('12/40')), frame('diff', diff)]);
      })
    );
    const { resumeLatestJob, parseGithubEvent } = await loadClient();
    const seen: string[] = [];
    const found = vi.fn();
    const resumed = await resumeLatestJob('github', parseGithubEvent, (e) => seen.push(e.event), undefined, undefined, found);
    expect(resumed).toBe(true);
    expect(found).toHaveBeenCalledOnce();
    expect(seen).toEqual(['progress', 'diff']);
    expect(calls[1]).toMatch(/\/jobs\/job_dddddddddddd\/stream\?from=0$/);
  });

  it('does nothing when there is no job, or an old finished one', async () => {
    const fetchMock = vi.fn(async () => new Response('{"detail":"No jobs yet."}', { status: 404 }));
    vi.stubGlobal('fetch', fetchMock);
    const { resumeLatestJob, parseGithubEvent } = await loadClient();
    expect(await resumeLatestJob('github', parseGithubEvent, () => undefined)).toBe(false);

    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ id: 'job_eeeeeeeeeeee', kind: 'github', status: 'done', finished_at: Date.now() / 1000 - 3600 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );
    const second = await loadClient();
    expect(await second.resumeLatestJob('github', second.parseGithubEvent, () => undefined)).toBe(false);
  });
});
