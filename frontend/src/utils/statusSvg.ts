import type { StatusKind } from './model';

/** Raw SVG markup, shared by the React icon and the Cytoscape renderer so both show the same glyph. */
export const STATUS_SVG_INNER: Record<StatusKind, string> = {
  active:
    '<circle cx="7" cy="7" r="6" fill="#2E9E6A"/><path d="M4.2 7.2l1.9 1.9 3.7-3.9" stroke="#fff" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  conflict:
    '<circle cx="7" cy="7" r="6" fill="#D9363E"/><path d="M7 4v3.6M7 9.9v.1" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>',
  stale:
    '<circle cx="7" cy="7" r="5.6" fill="none" stroke="#C77D00" stroke-width="1.6" stroke-dasharray="2.2 1.8"/>',
  superseded:
    '<circle cx="7" cy="7" r="5.6" fill="none" stroke="#9A9DA4" stroke-width="1.6"/><path d="M4.4 7h5.2" stroke="#9A9DA4" stroke-width="1.6" stroke-linecap="round"/>',
};

export function statusSvgString(status: StatusKind, size = 14): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 14 14">${STATUS_SVG_INNER[status]}</svg>`;
}

