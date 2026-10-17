const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function parseIsoDate(value?: string | null): { y: number; m: number; d: number } | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!match) return null;
  const m = Number(match[2]);
  if (m < 1 || m > 12) return null;
  return { y: Number(match[1]), m, d: Number(match[3]) };
}

/** "Jan 14" within the reference year, "Nov 2025" otherwise. Empty string if unparseable. */
export function formatShortDate(value?: string | null, now: Date = new Date()): string {
  const p = parseIsoDate(value);
  if (!p) return '';
  return p.y === now.getFullYear() ? `${MONTHS[p.m - 1]} ${p.d}` : `${MONTHS[p.m - 1]} ${p.y}`;
}

/** "Mar 12, 2026". Empty string if unparseable. */
export function formatLongDate(value?: string | null): string {
  const p = parseIsoDate(value);
  return p ? `${MONTHS[p.m - 1]} ${p.d}, ${p.y}` : '';
}

/**
 * Initials of the first person in a possibly composite name such as
 * "Laura Croft, Fiona Gallagher, Bob Martin".
 */
export function getInitials(name?: string | null): string {
  if (!name) return '?';
  const first = name.split(',')[0].trim();
  const parts = first.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export interface AvatarTone {
  bg: string;
  fg: string;
}

const AVATAR_TONES: AvatarTone[] = [
  { bg: '#DDE7F7', fg: '#2D4F8F' },
  { bg: '#F6E3D3', fg: '#7A4A1E' },
  { bg: '#E3EEDD', fg: '#3D5A2A' },
  { bg: '#EDE3F6', fg: '#5B3A7A' },
];

export const INACTIVE_AVATAR_TONE: AvatarTone = { bg: '#ECEDF0', fg: '#5A5E65' };

/** Stable pastel pair per name so a person keeps the same colour everywhere. */
export function getAvatarTone(name?: string | null, active = true): AvatarTone {
  if (!active) return INACTIVE_AVATAR_TONE;
  const key = (name ?? '').split(',')[0].trim();
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return AVATAR_TONES[hash % AVATAR_TONES.length];
}

export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

/** Question used by every "Ask about this" entry point. */
export function questionAboutDecision(title: string): string {
  return `Why was "${title}" decided, and is it still valid?`;
}

export function askHref(question: string): string {
  return `/?q=${encodeURIComponent(question)}`;
}

/** "212 ms" below a second, "1.4 s" above. */
export function formatMs(ms: number | undefined | null): string {
  if (ms === undefined || ms === null) return '';
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}
