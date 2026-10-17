import type { DemoStatus } from '../api/types';

/** "Demo data resets in N min" from GET /ingest/status, counting down locally between polls. */
export function resetCountdownText(status: DemoStatus | undefined, now: number = Date.now()): string {
  const minutes = status?.auto_reset_minutes ?? 10;
  if (!status) return `Demo data resets automatically ${minutes} minutes after the last ingest.`;
  if (!status.has_demo_data || !status.resets_at) {
    return `No demo data in the graph. Ingested sources reset automatically after ${minutes} idle minutes.`;
  }
  const left = Math.ceil((Date.parse(status.resets_at) - now) / 60_000);
  return left >= 1 ? `Demo data resets in ${left} min` : 'Demo data resets in under a minute';
}
