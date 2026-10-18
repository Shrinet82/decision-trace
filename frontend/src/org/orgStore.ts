/** Organizations created in this browser, remembered in localStorage (never required to work).
 *  The owner key is kept with the organization: it is what lets this browser change it. */
import type { OrgInfo } from '../api/types';

const KEY = 'dt.orgs.v1';
const MAX = 25;

export interface StoredOrg {
  id: string;
  name: string;
  created_at: string | null;
  owner_key?: string;
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

/** Remember an organization (and its owner key, if this browser just created it). */
export function rememberOrg(org: OrgInfo, ownerKey?: string): void {
  if (org.sample) return;
  const previous = loadOrgs().find((o) => o.id === org.id);
  const rest = loadOrgs().filter((o) => o.id !== org.id);
  const key = ownerKey ?? previous?.owner_key;
  save([{ id: org.id, name: org.name, created_at: org.created_at, ...(key ? { owner_key: key } : {}) }, ...rest]);
}

export function forgetOrg(id: string): void {
  save(loadOrgs().filter((o) => o.id !== id));
}

/** The owner key this browser holds for an organization, if any. */
export function getOwnerKey(id: string | null): string | undefined {
  if (!id) return undefined;
  return loadOrgs().find((o) => o.id === id)?.owner_key;
}
