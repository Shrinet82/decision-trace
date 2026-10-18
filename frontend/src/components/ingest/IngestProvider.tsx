import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useChanges } from '../../api/hooks';
import type { IngestDiff } from '../../api/types';
import { recentDiff } from '../../utils/changes';
import { IngestContext, type IngestContextValue, type IngestTab } from './ingestContext';
import { IngestDrawer } from './IngestDrawer';

/**
 * Holds the "Add source" drawer state and the latest ingest diff for the whole app. On load the
 * latest diff is seeded from GET /changes?limit=1 when that ingest happened in the last 30 minutes.
 */
export const IngestProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState<IngestTab>('paste');
  const [latestDiff, setLatestDiffState] = useState<IngestDiff | null>(null);
  const touched = useRef(false);
  const changes = useChanges(10);

  useEffect(() => {
    if (touched.current || !changes.data) return;
    touched.current = true;
    const diff = recentDiff(changes.data.find((c) => c.kind === 'ingest' && !c.reverted));
    if (diff) setLatestDiffState(diff);
  }, [changes.data]);

  const setLatestDiff = useCallback((diff: IngestDiff | null) => {
    touched.current = true;
    setLatestDiffState(diff);
  }, []);
  const openDrawer = useCallback((requested?: unknown) => {
    // onClick handlers pass the click event; only a tab name selects a tab
    if (requested === 'paste' || requested === 'files' || requested === 'github') setTab(requested);
    setDrawerOpen(true);
  }, []);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const value = useMemo<IngestContextValue>(
    () => ({ drawerOpen, tab, setTab, openDrawer, closeDrawer, latestDiff, setLatestDiff }),
    [drawerOpen, tab, openDrawer, closeDrawer, latestDiff, setLatestDiff]
  );

  return (
    <IngestContext.Provider value={value}>
      {children}
      <IngestDrawer />
    </IngestContext.Provider>
  );
};
