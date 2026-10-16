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
