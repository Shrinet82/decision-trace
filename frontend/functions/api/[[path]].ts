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

  // Entity names: letters, digits, spaces and a few punctuation marks only
  const NAME = "[A-Za-z0-9 _.&'-]{1,80}";
  const entityDetail = new RegExp(`^/(systems|people)/${NAME}$`);
  // Source keys are ticket IDs, meeting / document titles or record names (titles may hold : , ( ))
  const sourceDetail = new RegExp(
    "^/sources/(ticket|meeting|document|person|team|project|system)/[A-Za-z0-9 _.&'(),:-]{1,120}$"
  );

  // Strict whitelist check
  const isWhitelisted =
    (method === 'GET' && normalizedPath === '/health') ||
    (method === 'GET' && normalizedPath === '/decisions') ||
    (method === 'GET' && /^\/decisions\/[a-zA-Z0-9_-]+$/.test(normalizedPath)) ||
    (method === 'GET' && normalizedPath === '/graph') ||
    (method === 'GET' && (normalizedPath === '/systems' || normalizedPath === '/people')) ||
    (method === 'GET' && entityDetail.test(normalizedPath)) ||
    (method === 'POST' && normalizedPath === '/ask') ||
    (method === 'POST' && normalizedPath === '/ask/stream') ||
    (method === 'GET' && normalizedPath === '/sources') ||
    (method === 'GET' && sourceDetail.test(normalizedPath)) ||
    (method === 'GET' && normalizedPath === '/ingest/status') ||
    (method === 'POST' && normalizedPath === '/ingest') ||
    (method === 'POST' && normalizedPath === '/ingest/reset') ||
    (method === 'GET' && normalizedPath === '/changes');

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

  const upstream = await fetch(modifiedRequest);

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
