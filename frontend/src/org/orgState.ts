/**
 * The organization the app is currently showing. Set synchronously by the org layout route while it
 * renders, so API helpers and query keys can read it without threading a parameter everywhere.
 * `null` is the sample organization (the unprefixed API routes).
 */
let currentOrg: string | null = null;

export function setCurrentOrg(slug: string | null): void {
  currentOrg = slug;
}

export function getCurrentOrg(): string | null {
  return currentOrg;
}

/** `/app` for the sample organization, `/app/o/<slug>` for any other. */
export function appBase(slug: string | null = currentOrg): string {
  return slug ? `/app/o/${encodeURIComponent(slug)}` : '/app';
}

/** Prefix for API paths: empty for the sample organization, `/orgs/<slug>` otherwise. */
export function apiOrgPrefix(slug: string | null = currentOrg): string {
  return slug ? `/orgs/${encodeURIComponent(slug)}` : '';
}

/** Adds the current app base to an in-app absolute path. External and already-based paths pass through. */
export function withBase(to: string, slug: string | null = currentOrg): string {
  if (!to.startsWith('/') || to.startsWith('//')) return to;
  if (to === '/app' || to.startsWith('/app/') || to.startsWith('/app?')) return to;
  const base = appBase(slug);
  if (to === '/') return base;
  if (to.startsWith('/?')) return `${base}${to.slice(1)}`;
  return `${base}${to}`;
}

/** Removes the app base from a pathname, so page code can compare against `/explore` and the like. */
export function stripBase(pathname: string): string {
  const match = /^\/app(?:\/o\/[^/]+)?(\/.*)?$/.exec(pathname);
  if (!match) return pathname;
  return match[1] ?? '/';
}
