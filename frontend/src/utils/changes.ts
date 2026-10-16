import type { ChangeEntry, HealthStatus, IngestDiff } from '../api/types';

/** How long the latest ingest counts as "just now" when seeded from GET /changes. */
export const RECENT_CHANGE_MS = 30 * 60 * 1000;

const same = (a: string | undefined | null, b: string | undefined | null) =>
  Boolean(a && b && a.toLowerCase() === b.toLowerCase());

/** The key part of a `Label:key` id. */
export function nodeKey(id: string): string {
  const colon = id.indexOf(':');
  return colon === -1 ? id : id.slice(colon + 1);
}

export function nodeLabel(id: string): string {
  const colon = id.indexOf(':');
  return colon === -1 ? '' : id.slice(0, colon);
}

/** A decision added by the diff, or whose health it changed. */
export function isDecisionChanged(diff: IngestDiff | null | undefined, code: string | null | undefined): boolean {
  if (!diff || !code) return false;
  return (
    diff.nodes_added.some((n) => n.label === 'Decision' && same(n.decision_code, code)) ||
    diff.status_changes.some((c) => same(c.decision_code, code))
  );
}

/** A system whose orphaned flag changed, that was added, or that a newly added decision is about. */
export function isSystemChanged(diff: IngestDiff | null | undefined, name: string | null | undefined): boolean {
  if (!diff || !name) return false;
  if (diff.orphan_changes.some((c) => same(c.system, name))) return true;
  if (diff.nodes_added.some((n) => n.label === 'System' && same(n.name, name))) return true;
  const newDecisions = new Set(diff.nodes_added.filter((n) => n.label === 'Decision').map((n) => n.id));
  return diff.edges_added.some(
    (e) =>
      (newDecisions.has(e.source) && nodeLabel(e.target) === 'System' && same(nodeKey(e.target), name)) ||
      (newDecisions.has(e.target) && nodeLabel(e.source) === 'System' && same(nodeKey(e.source), name))
  );
}

/** A person whose record the diff changed, or who was added. */
export function isPersonChanged(diff: IngestDiff | null | undefined, name: string | null | undefined): boolean {
  if (!diff || !name) return false;
  return (
    diff.person_changes.some((c) => same(c.name, name)) ||
    diff.nodes_added.some((n) => n.label === 'Person' && same(n.name, name))
  );
}

/** The latest ingest diff from the change log, if it is recent enough to call "just now". */
export function recentDiff(entry: ChangeEntry | undefined, now = Date.now()): IngestDiff | null {
  if (!entry || entry.kind !== 'ingest' || !entry.diff) return null;
  const at = Date.parse(entry.created_at);
  if (Number.isNaN(at) || now - at > RECENT_CHANGE_MS || at - now > RECENT_CHANGE_MS) return null;
  return entry.diff;
}

export const HEALTH_LABEL: Record<HealthStatus, string> = {
  active: 'Active',
  superseded: 'Superseded',
  contradicted: 'Contradicted',
  possibly_stale: 'Possibly stale',
};
