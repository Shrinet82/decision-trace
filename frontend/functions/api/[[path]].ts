export async function onRequest(context: {
  request: Request;
}): Promise<Response> {
  const url = new URL(context.request.url);
  const targetPath = url.pathname.replace(/^\/api/, '');
  const targetUrl = `https://decision-trace-api-production.up.railway.app${targetPath}${url.search}`;

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
