import type { Expert } from '../api/types';

/** Evidence kinds with the weight the backend ranks by (decided x3, owns x3, meetings x2, tickets x1). */
export const EVIDENCE = [
  { key: 'decided', label: 'decided', plural: 'decided', weight: 3, color: '#4F5BD5' },
  { key: 'owns', label: 'owns', plural: 'owns', weight: 3, color: '#12807A' },
  { key: 'meetings', label: 'meeting', plural: 'meetings', weight: 2, color: '#C98A00' },
  { key: 'tickets', label: 'ticket', plural: 'tickets', weight: 1, color: '#8A8E95' },
] as const;

export function evidenceSummary(e: Expert): string {
  return EVIDENCE.filter((k) => e.evidence[k.key] > 0)
    .map((k) => `${e.evidence[k.key]} ${e.evidence[k.key] === 1 ? k.label : k.plural}`)
    .join(' · ');
}
