import { useEffect } from 'react';

export const APP_NAME = 'Decision Trace';

/** "<page> · Decision Trace" in the browser tab and history. */
export function useDocumentTitle(page?: string | null): void {
  useEffect(() => {
    document.title = page ? `${page} · ${APP_NAME}` : `${APP_NAME} · Why did we decide that?`;
  }, [page]);
}
