/**
 * Cloudflare Pages Functions API Reverse Proxy
 *
 * Enforces:
 * 1. Strict path normalization and path traversal blocking (e.g. /decisions/../admin).
 * 2. Strict endpoint and HTTP method whitelisting:
 *    - GET  /health
 *    - GET  /decisions
 *    - GET  /decisions/:ref   (DEC code, id)
 *    - GET  /graph
 *    - GET  /systems, /systems/:name
 *    - GET  /people,  /people/:name
 *    - POST /ask
 *    - POST /ask/stream       (text/event-stream response, streamed through unbuffered)
 *    - GET  /sources, /sources/:kind/:key
 *    - POST /ingest           (text/event-stream response, streamed through unbuffered)
 *    - POST /ingest/reset
 *    - GET  /ingest/status
 *    - GET  /changes
 *    - GET  /attention
 *    - POST /ingest/batch, POST /ingest/github   (streams)
 *    - POST /orgs, GET /orgs (showcase list), GET|DELETE /orgs/:id
 *    - everything above under /orgs/:id/... for a user organization
 * 3. Blocks all administrative (/admin), documentation (/docs, /redoc, /openapi.json),
 *    and unwhitelisted routes.
 */

export async function onRequest(context: {
  request: Request;
}): Promise<Response> {
  const url = new URL(context.request.url);
  const method = context.request.method.toUpperCase();

  // Strip leading /api prefix
  let rawPath = url.pathname.replace(/^\/api(\/|$)/, '/');
  if (!rawPath.startsWith('/')) {
    rawPath = '/' + rawPath;
  }

  // Decode URI component to detect encoded directory traversal (%2e%2e)
  let decodedPath: string;
  try {
    decodedPath = decodeURIComponent(rawPath);
  } catch {
    return new Response(JSON.stringify({ error: 'Malformed path encoding' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Traversal and malformed path checks
  if (
    decodedPath.includes('..') ||
    decodedPath.includes('\\') ||
    decodedPath.includes('//')
  ) {
    return new Response(JSON.stringify({ error: 'Directory traversal not allowed' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Path normalization: collapse segments
  const segments = decodedPath.split('/').filter(Boolean);
  const normalizedPath = '/' + segments.join('/');

  // Organizations: POST /orgs creates one, GET|DELETE /orgs/:id reads or deletes it, and
  // /orgs/:id/<path> is any whitelisted route on that organization.
  const ORG_ID = '[a-z0-9][a-z0-9-]{0,63}';
  let orgPath = normalizedPath;
  const orgMatch = new RegExp(`^/orgs/(${ORG_ID})(/.*)?$`).exec(normalizedPath);
  if ((method === 'POST' || method === 'GET') && normalizedPath === '/orgs') {
    orgPath = method === 'GET' ? '/orgs:list' : '/orgs';
  } else if (orgMatch && !orgMatch[2]) {
    orgPath = method === 'GET' || method === 'DELETE' ? '/orgs/:id' : '/blocked';
  } else if (orgMatch) {
    orgPath = orgMatch[2];
  } else if (normalizedPath === '/orgs' || normalizedPath.startsWith('/orgs/')) {
    orgPath = '/blocked';
  }

  // Entity names: letters, digits, spaces and a few punctuation marks only
  const NAME = "[A-Za-z0-9 _.&'-]{1,80}";
  const entityDetail = new RegExp(`^/(systems|people)/${NAME}$`);
  // Source keys are ticket IDs, meeting / document titles or record names (titles may hold : , ( ))
  const sourceDetail = new RegExp(
    "^/sources/(ticket|meeting|document|person|team|project|system)/[A-Za-z0-9 _.&'(),:-]{1,120}$"
  );

  // Strict whitelist check
  const isWhitelisted =
    (method === 'GET' && orgPath === '/health') ||
    (method === 'GET' && orgPath === '/decisions') ||
    (method === 'GET' && /^\/decisions\/[a-zA-Z0-9_-]+$/.test(orgPath)) ||
    (method === 'GET' && orgPath === '/graph') ||
    (method === 'GET' && (orgPath === '/systems' || orgPath === '/people')) ||
    (method === 'GET' && entityDetail.test(orgPath)) ||
    (method === 'POST' && orgPath === '/ask') ||
    (method === 'POST' && orgPath === '/ask/stream') ||
    (method === 'GET' && orgPath === '/sources') ||
    (method === 'GET' && sourceDetail.test(orgPath)) ||
    (method === 'GET' && orgPath === '/ingest/status') ||
    (method === 'POST' && orgPath === '/ingest') ||
    (method === 'POST' && orgPath === '/ingest/reset') ||
    (method === 'GET' && orgPath === '/changes') ||
    (method === 'GET' && orgPath === '/attention') ||
    (method === 'POST' && orgPath === '/ingest/batch') ||
    (method === 'POST' && orgPath === '/ingest/github') ||
    (method === 'POST' && orgPath === '/orgs') ||
    (method === 'GET' && orgPath === '/orgs:list') ||
    ((method === 'GET' || method === 'DELETE') && orgPath === '/orgs/:id');

  if (!isWhitelisted) {
    return new Response(JSON.stringify({ error: 'Endpoint not found or method not allowed' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const targetPath = segments.map((segment) => encodeURIComponent(segment)).join('/');
  const targetUrl = `https://decision-trace-api-production.up.railway.app/${targetPath}${url.search}`;

  const requestHeaders = new Headers(context.request.headers);
  requestHeaders.set('Host', 'decision-trace-api-production.up.railway.app');
  // Per-IP rate limits (POST /ingest) need the visitor's address, not the proxy's. Overwrite
  // rather than append so a client cannot spoof it through the proxy.
  const clientIp = context.request.headers.get('CF-Connecting-IP');
  if (clientIp) {
    requestHeaders.set('X-Forwarded-For', clientIp);
    requestHeaders.set('X-Real-IP', clientIp);
  }

  const modifiedRequest = new Request(targetUrl, {
    method: context.request.method,
    headers: requestHeaders,
    body: context.request.body,
    redirect: 'follow',
  });

  // Never wait forever on the API: plain requests get 30 s; the two streams get long enough for
  // their own per-step limits (Ask 45 s per model call, ingest several calls).
  const isStream =
    orgPath === '/ask/stream' || orgPath === '/ingest' || orgPath === '/ingest/batch' || orgPath === '/ingest/github';
  let upstream: Response;
  try {
    upstream = await fetch(modifiedRequest, {
      signal: AbortSignal.timeout(isStream ? 170_000 : 30_000),
    });
  } catch (error) {
    const timedOut = error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError');
    return new Response(
      JSON.stringify({
        detail: timedOut
          ? 'The API took too long to respond. Try again in a moment.'
          : 'The API is unreachable right now. Try again in a moment.',
      }),
      { status: timedOut ? 504 : 502, headers: { 'Content-Type': 'application/json' } }
    );
  }

  // Server-sent events: hand the body stream straight back (never buffer it) and tell any
  // intermediary not to compress or transform it, which would delay events.
  const contentType = upstream.headers.get('Content-Type') ?? '';
  if (contentType.includes('text/event-stream')) {
    const headers = new Headers(upstream.headers);
    headers.set('Cache-Control', 'no-cache, no-transform');
    headers.set('X-Accel-Buffering', 'no');
    headers.delete('Content-Length');
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  }

  return upstream;
}
