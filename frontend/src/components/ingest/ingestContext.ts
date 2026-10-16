import { createContext, useContext } from 'react';
import type { IngestDiff } from '../../api/types';

export interface IngestContextValue {
  drawerOpen: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
  /** Diff of the most recent ingest in this session (or seeded from GET /changes). */
  latestDiff: IngestDiff | null;
  setLatestDiff: (diff: IngestDiff | null) => void;
}

export const IngestContext = createContext<IngestContextValue | null>(null);

/** Null outside the app shell (for example in page tests), where ingest UI is not shown. */
export function useIngest(): IngestContextValue | null {
  return useContext(IngestContext);
}

/** The latest ingest diff, or null when none is known. */
export function useLatestDiff(): IngestDiff | null {
  return useContext(IngestContext)?.latestDiff ?? null;
}
