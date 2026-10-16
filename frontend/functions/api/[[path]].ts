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

  // Strict whitelist check
  const isWhitelisted =
    (method === 'GET' && normalizedPath === '/health') ||
    (method === 'GET' && normalizedPath === '/decisions') ||
    (method === 'GET' && /^\/decisions\/[a-zA-Z0-9_-]+$/.test(normalizedPath)) ||
    (method === 'GET' && normalizedPath === '/graph') ||
    (method === 'GET' && (normalizedPath === '/systems' || normalizedPath === '/people')) ||
    (method === 'GET' && entityDetail.test(normalizedPath)) ||
    (method === 'POST' && normalizedPath === '/ask');

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

  const modifiedRequest = new Request(targetUrl, {
    method: context.request.method,
    headers: requestHeaders,
    body: context.request.body,
    redirect: 'follow',
  });

  return fetch(modifiedRequest);
}
