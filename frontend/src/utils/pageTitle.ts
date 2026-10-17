const SECTIONS: Record<string, string> = {
  ask: 'Ask',
  decisions: 'Decisions',
  systems: 'Systems',
  people: 'People',
  explore: 'Explore',
  graph: 'Explore',
  sources: 'Sources',
  agents: 'Connect an agent',
};

function decode(part: string): string {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

/** The page name for a path, used for the browser tab title; null for Home. */
export function pageTitleForPath(pathname: string): string | null {
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length === 0) return null;
  const section = SECTIONS[parts[0]];
  if (!section || parts.length > 2) return 'Page not found';
  return parts[1] ? decode(parts[1]) : section;
}
