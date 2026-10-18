import { useEffect, useState } from 'react';
import { loadOrgs, type StoredOrg } from './orgStore';

/** The organizations remembered in this browser; updates when one is added or forgotten. */
export function useStoredOrgs(): StoredOrg[] {
  const [orgs, setOrgs] = useState<StoredOrg[]>(() => loadOrgs());
  useEffect(() => {
    const refresh = () => setOrgs(loadOrgs());
    window.addEventListener('dt-orgs-changed', refresh);
    window.addEventListener('storage', refresh);
    return () => {
      window.removeEventListener('dt-orgs-changed', refresh);
      window.removeEventListener('storage', refresh);
    };
  }, []);
  return orgs;
}
