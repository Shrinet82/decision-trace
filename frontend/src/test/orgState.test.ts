import { describe, expect, it } from 'vitest';
import { apiOrgPrefix, appBase, stripBase, withBase } from '../org/orgState';

describe('org paths', () => {
  it('the sample organization lives under /app with no API prefix', () => {
    expect(appBase(null)).toBe('/app');
    expect(apiOrgPrefix(null)).toBe('');
    expect(withBase('/decisions/DEC-11', null)).toBe('/app/decisions/DEC-11');
    expect(withBase('/', null)).toBe('/app');
    expect(withBase('/?q=x', null)).toBe('/app?q=x');
  });

  it('a user organization is prefixed in the app and in the API', () => {
    expect(appBase('acme-3f9a1c')).toBe('/app/o/acme-3f9a1c');
    expect(apiOrgPrefix('acme-3f9a1c')).toBe('/orgs/acme-3f9a1c');
    expect(withBase('/explore?node=x', 'acme-3f9a1c')).toBe('/app/o/acme-3f9a1c/explore?node=x');
  });

  it('leaves external, protocol-relative and already-based paths alone', () => {
    expect(withBase('https://example.com/x', 'a')).toBe('https://example.com/x');
    expect(withBase('//cdn.example.com', 'a')).toBe('//cdn.example.com');
    expect(withBase('/app/agents', 'a')).toBe('/app/agents');
  });

  it('strips the base so pages can compare against /explore and friends', () => {
    expect(stripBase('/app')).toBe('/');
    expect(stripBase('/app/explore')).toBe('/explore');
    expect(stripBase('/app/o/acme-3f9a1c/decisions/DEC-11')).toBe('/decisions/DEC-11');
    expect(stripBase('/decisions')).toBe('/decisions');
  });
});
