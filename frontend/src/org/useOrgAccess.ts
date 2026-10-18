import { useOrgInfo } from '../api/hooks';
import { useOrgSlug } from './OrgContext';
import { useStoredOrgs } from './useOrgs';

export interface OrgAccess {
  /** Acme and the showcase organizations: shared, with tagged demo data that resets. */
  isSample: boolean;
  /** Whether this browser may add to the organization (samples take demo data; your own need the key). */
  canWrite: boolean;
  slug: string | null;
}

/** What the current visitor can do in the current organization. */
export function useOrgAccess(): OrgAccess {
  const slug = useOrgSlug();
  const info = useOrgInfo(slug);
  const stored = useStoredOrgs();
  const isSample = slug === null || info.data?.sample === true;
  const hasKey = slug !== null && stored.some((o) => o.id === slug && Boolean(o.owner_key));
  return { isSample, canWrite: isSample || hasKey, slug };
}
