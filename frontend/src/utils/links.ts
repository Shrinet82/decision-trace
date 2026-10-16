/** Routes for entity pages. Names are URL-encoded (people and systems may contain spaces). */
export const decisionHref = (codeOrId: string) => `/decisions/${encodeURIComponent(codeOrId)}`;
export const systemHref = (name: string) => `/systems/${encodeURIComponent(name)}`;
export const personHref = (name: string) => `/people/${encodeURIComponent(name)}`;
export const exploreHref = (nodeId: string) => `/explore?node=${encodeURIComponent(nodeId)}`;

/** Splits text around DEC-NN codes so each can be rendered as a link. */
export function splitDecisionCodes(text: string): { text: string; code?: string }[] {
  const parts: { text: string; code?: string }[] = [];
  const pattern = /\bDEC-\d{2,}\b/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index) });
    parts.push({ text: match[0], code: match[0] });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
