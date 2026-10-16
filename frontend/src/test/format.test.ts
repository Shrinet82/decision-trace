import { describe, it, expect } from 'vitest';
import { formatLongDate, formatShortDate, getAvatarTone, getInitials, truncate } from '../utils/format';

describe('format helpers', () => {
  it('formats short dates relative to the reference year', () => {
    const now = new Date('2026-06-01T00:00:00Z');
    expect(formatShortDate('2026-01-14', now)).toBe('Jan 14');
    expect(formatShortDate('2025-11-30', now)).toBe('Nov 2025');
    expect(formatShortDate(undefined, now)).toBe('');
    expect(formatShortDate('not a date', now)).toBe('');
  });

  it('formats long dates', () => {
    expect(formatLongDate('2026-03-12')).toBe('Mar 12, 2026');
    expect(formatLongDate('')).toBe('');
  });

  it('derives initials, using only the first person of composite names', () => {
    expect(getInitials('Priya Nair')).toBe('PN');
    expect(getInitials('Laura Croft, Fiona Gallagher, Bob Martin')).toBe('LC');
    expect(getInitials(null)).toBe('?');
  });

  it('keeps avatar tone stable per name and muted for inactive people', () => {
    expect(getAvatarTone('Alice Vance')).toEqual(getAvatarTone('Alice Vance'));
    expect(getAvatarTone('Alice Vance', false).bg).toBe('#ECEDF0');
  });

  it('truncates with an ellipsis', () => {
    expect(truncate('abcdef', 4)).toBe('abc…');
    expect(truncate('abc', 4)).toBe('abc');
  });
});
