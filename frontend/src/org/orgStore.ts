/** Organizations created in this browser, remembered in localStorage (never required to work). */
import type { OrgInfo } from '../api/types';

const KEY = 'dt.orgs.v1';
const MAX = 25;

export interface StoredOrg {
  id: string;
  name: string;
  created_at: string | null;
}

export function loadOrgs(): StoredOrg[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((o): o is StoredOrg => Boolean(o) && typeof o.id === 'string' && typeof o.name === 'string')
      .slice(0, MAX);
  } catch {
    return [];
  }
}

function save(orgs: StoredOrg[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(orgs.slice(0, MAX)));
  } catch {
    // Storage can be blocked; the organization still works for this visit.
  }
  window.dispatchEvent(new Event('dt-orgs-changed'));
}

export function rememberOrg(org: OrgInfo): void {
  if (org.sample) return;
  const rest = loadOrgs().filter((o) => o.id !== org.id);
  save([{ id: org.id, name: org.name, created_at: org.created_at }, ...rest]);
}

export function forgetOrg(id: string): void {
  save(loadOrgs().filter((o) => o.id !== id));
}
