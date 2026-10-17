export interface QuoteMatch {
  before: string;
  match: string;
  after: string;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Finds `quote` inside `text`, ignoring case and differences in whitespace (line wraps). Surrounding
 * quotation marks and a trailing full stop on the quote are tolerated. Returns null when absent.
 */
export function findQuote(text: string, quote: string | null | undefined): QuoteMatch | null {
  if (!quote) return null;
  const candidates = [quote.trim(), quote.trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, '').replace(/\.$/, '').trim()];
  for (const candidate of candidates) {
    if (candidate.length === 0) continue;
    const pattern = candidate.split(/\s+/).map(escapeRegExp).join('\\s+');
    const found = new RegExp(pattern, 'i').exec(text);
    if (found) {
      return {
        before: text.slice(0, found.index),
        match: found[0],
        after: text.slice(found.index + found[0].length),
      };
    }
  }
  return null;
}

export interface Segment {
  text: string;
  /** Index into the quotes array when this segment is a highlighted quote. */
  quote?: number;
}

/**
 * Splits `text` into plain and highlighted segments, one highlight per quote found (case and
 * whitespace insensitive, as findQuote). Overlapping matches keep the earlier one.
 */
export function highlightAll(text: string, quotes: (string | null | undefined)[]): Segment[] {
  const ranges: { start: number; end: number; quote: number }[] = [];
  quotes.forEach((q, i) => {
    const m = findQuote(text, q);
    if (m) ranges.push({ start: m.before.length, end: m.before.length + m.match.length, quote: i });
  });
  ranges.sort((a, b) => a.start - b.start);
  const segments: Segment[] = [];
  let at = 0;
  for (const r of ranges) {
    if (r.start < at) continue;
    if (r.start > at) segments.push({ text: text.slice(at, r.start) });
    segments.push({ text: text.slice(r.start, r.end), quote: r.quote });
    at = r.end;
  }
  if (at < text.length) segments.push({ text: text.slice(at) });
  return segments;
}
