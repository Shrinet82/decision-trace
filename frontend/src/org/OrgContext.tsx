import React, { createContext, useContext } from 'react';

const OrgContext = createContext<string | null>(null);

export const OrgProvider: React.FC<{ slug: string | null; children: React.ReactNode }> = ({ slug, children }) => (
  <OrgContext.Provider value={slug}>{children}</OrgContext.Provider>
);

/** The current organization's slug, or null for the sample organization. */
export function useOrgSlug(): string | null {
  return useContext(OrgContext);
}
