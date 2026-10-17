import { describe, expect, it } from 'vitest';
import { CLIENT_SNIPPETS, MCP_TOOLS, MCP_URL } from '../config/mcp';
import { askHref, formatRelative } from '../utils/format';

describe('formatRelative', () => {
  const now = Date.parse('2026-10-17T12:00:00Z');
  it.each([
    ['2026-10-17T11:59:40Z', 'just now'],
    ['2026-10-17T11:55:00Z', '5 min ago'],
    ['2026-10-17T09:00:00Z', '3 h ago'],
    ['2026-10-15T12:00:00Z', '2 d ago'],
    ['2026-05-01T12:00:00Z', '2026-05-01'],
  ])('%s -> %s', (value, expected) => expect(formatRelative(value, now)).toBe(expected));
  it('is empty for a missing or invalid time', () => {
    expect(formatRelative(undefined, now)).toBe('');
    expect(formatRelative('nope', now)).toBe('');
  });
});

describe('agent connection details', () => {
  it('points every snippet at the MCP endpoint', () => {
    for (const s of CLIENT_SNIPPETS) expect(s.code).toContain(MCP_URL);
    expect(MCP_URL).toMatch(/\/mcp$/);
  });
  it('lists the seven tools, only add_source writing', () => {
    expect(MCP_TOOLS.map((t) => t.name).sort()).toEqual(
      ['add_source', 'ask', 'find_conflicts', 'get_decision', 'impact_of', 'list_decisions', 'who_knows']
    );
    expect(MCP_TOOLS.filter((t) => t.writes).map((t) => t.name)).toEqual(['add_source']);
  });
  it('builds ask links under /ask', () => {
    expect(askHref('Why Kafka?')).toBe('/ask?q=Why%20Kafka%3F');
  });
});
