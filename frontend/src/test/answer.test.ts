import { describe, it, expect } from 'vitest';
import { isNotFoundAnswer, parseAnswer, tokenizeInline, withCitationMarks } from '../utils/answer';

describe('answer parsing', () => {
  it('tokenizes bold and code', () => {
    expect(tokenizeInline('a **b** `c` d')).toEqual([
      { kind: 'text', text: 'a ' },
      { kind: 'bold', text: 'b' },
      { kind: 'text', text: ' ' },
      { kind: 'code', text: 'c' },
      { kind: 'text', text: ' d' },
    ]);
  });

  it('tokenizes single-asterisk italics without eating bullets', () => {
    expect(tokenizeInline('during the *Platform Sync* meeting')).toEqual([
      { kind: 'text', text: 'during the ' },
      { kind: 'italic', text: 'Platform Sync' },
      { kind: 'text', text: ' meeting' },
    ]);
    const blocks = parseAnswer('*   Item one\n*   Item two');
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe('list');
  });

  it('parses paragraphs, numbered lists and nested bullets', () => {
    const blocks = parseAnswer(
      'Intro line.\n\n1.  **One:** first\n    *   Sub a\n    *   Sub b\n2.  Two\n\nTail.'
    );
    expect(blocks.map((b) => b.kind)).toEqual(['paragraph', 'list', 'paragraph']);
    const list = blocks[1];
    if (list.kind !== 'list') throw new Error('expected list');
    expect(list.ordered).toBe(true);
    expect(list.items).toHaveLength(2);
    expect(list.items[0].children).toHaveLength(2);
  });

  it('marks each citation once, after its first mention', () => {
    const citations = [
      { type: 'ticket' as const, id: 'TICK-101', title: 'Latency' },
      { type: 'ticket' as const, id: 'TICK-110', title: 'Memory pressure' },
    ];
    const used = new Set<number>();
    const first = withCitationMarks(tokenizeInline('See TICK-101 and TICK-101 again.'), citations, used);
    expect(first.filter((t) => t.kind === 'cite')).toEqual([{ kind: 'cite', index: 0 }]);
    const second = withCitationMarks(tokenizeInline('Also (TICK-110).'), citations, used);
    expect(second.filter((t) => t.kind === 'cite')).toEqual([{ kind: 'cite', index: 1 }]);
    // Text is preserved around the marker
    const flat = first.map((t) => ('text' in t ? t.text : '')).join('');
    expect(flat).toBe('See TICK-101 and TICK-101 again.');
  });

  it('adds no marker for citations the text never mentions', () => {
    const out = withCitationMarks(
      tokenizeInline('Nothing relevant.'),
      [{ type: 'ticket', id: 'TICK-999', title: 'Other' }],
      new Set()
    );
    expect(out.some((t) => t.kind === 'cite')).toBe(false);
  });

  it('detects not-found answers', () => {
    expect(isNotFoundAnswer('The answer is not found in the Company Brain.', 0)).toBe(true);
    expect(isNotFoundAnswer('Something', 0)).toBe(true);
    expect(isNotFoundAnswer('Alice decided.', 2)).toBe(false);
  });
});
