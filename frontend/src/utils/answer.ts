import type { Citation } from '../api/types';

export type InlineToken =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'italic'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'cite'; index: number };

export interface ListItem {
  tokens: InlineToken[];
  children: InlineToken[][];
}

export type AnswerBlock =
  | { kind: 'paragraph'; tokens: InlineToken[] }
  | { kind: 'list'; ordered: boolean; items: ListItem[] };

const ORDERED = /^(\s*)\d+[.)]\s+(.*)$/;
const BULLET = /^(\s*)[*\-•]\s+(.*)$/;

/** Splits inline markdown (bold, italic, code) into tokens. */
export function tokenizeInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  const pattern = /\*\*(.+?)\*\*|\*([^*\s][^*]*?)\*|`([^`]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) tokens.push({ kind: 'text', text: text.slice(last, match.index) });
    if (match[1] !== undefined) tokens.push({ kind: 'bold', text: match[1] });
    else if (match[2] !== undefined) tokens.push({ kind: 'italic', text: match[2] });
    else tokens.push({ kind: 'code', text: match[3] });
    last = match.index + match[0].length;
  }
  if (last < text.length) tokens.push({ kind: 'text', text: text.slice(last) });
  return tokens;
}

/**
 * Parses the subset of markdown the model emits (paragraphs, bold, numbered and
 * bulleted lists with one nesting level) into blocks.
 */
export function parseAnswer(answer: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: ListItem[] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ kind: 'paragraph', tokens: tokenizeInline(paragraph.join(' ').trim()) });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      blocks.push({ kind: 'list', ordered: list.ordered, items: list.items });
      list = null;
    }
  };

  for (const rawLine of answer.replace(/\r\n/g, '\n').split('\n')) {
    if (rawLine.trim() === '') {
      flushParagraph();
      flushList();
      continue;
    }
    const ordered = ORDERED.exec(rawLine);
    const bullet = BULLET.exec(rawLine);

    if (ordered && ordered[1].length < 2) {
      flushParagraph();
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push({ tokens: tokenizeInline(ordered[2].trim()), children: [] });
    } else if (bullet && list && list.items.length > 0 && bullet[1].length >= 2) {
      list.items[list.items.length - 1].children.push(tokenizeInline(bullet[2].trim()));
    } else if (bullet) {
      flushParagraph();
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push({ tokens: tokenizeInline(bullet[2].trim()), children: [] });
    } else if (list && list.items.length > 0) {
      // Continuation line of the previous list item
      const item = list.items[list.items.length - 1];
      item.tokens = [...item.tokens, { kind: 'text', text: ` ${rawLine.trim()}` }];
    } else {
      paragraph.push(rawLine.trim());
    }
  }
  flushParagraph();
  flushList();
  return blocks;
}

/**
 * Inserts a citation marker token after the first mention of each citation
 * (by id, or by title). `used` is shared across the whole answer so each
 * citation is marked once. Citations never mentioned get no inline marker.
 */
export function withCitationMarks(
  tokens: InlineToken[],
  citations: Citation[],
  used: Set<number>
): InlineToken[] {
  const out: InlineToken[] = [];
  for (const token of tokens) {
    if (token.kind === 'cite') {
      out.push(token);
      continue;
    }
    let remaining = token.text;
    // A token may mention several citations; split at each earliest unused mention.
    for (;;) {
      let best: { at: number; end: number; index: number } | null = null;
      citations.forEach((citation, index) => {
        if (used.has(index)) return;
        for (const needle of [citation.id, citation.title]) {
          if (!needle) continue;
          const at = remaining.toLowerCase().indexOf(needle.toLowerCase());
          if (at >= 0 && (!best || at < best.at)) {
            best = { at, end: at + needle.length, index };
          }
        }
      });
      if (!best) break;
      const hit = best as { at: number; end: number; index: number };
      used.add(hit.index);
      out.push({ ...token, text: remaining.slice(0, hit.end) });
      out.push({ kind: 'cite', index: hit.index });
      remaining = remaining.slice(hit.end);
      if (remaining === '') break;
    }
    if (remaining !== '' || out.length === 0) out.push({ ...token, text: remaining });
  }
  return out;
}

export function isNotFoundAnswer(answer: string, citationCount: number): boolean {
  const a = answer.toLowerCase();
  return citationCount === 0 || a.includes('not found in the company brain') || a.includes('the answer is not found');
}

/** DOM id of the source card for citation `index` (0-based) in a given thread turn. */
export const citeAnchor = (turnKey: string, index: number) => `cite-${turnKey}-${index + 1}`;
