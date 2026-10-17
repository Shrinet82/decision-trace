import { describe, expect, it } from 'vitest';
import { pageTitleForPath } from '../utils/pageTitle';

describe('pageTitleForPath', () => {
  it.each([
    ['/', null],
    ['/ask', 'Ask'],
    ['/decisions', 'Decisions'],
    ['/decisions/DEC-11', 'DEC-11'],
    ['/systems/Elasticsearch', 'Elasticsearch'],
    ['/people/Alice%20Vance', 'Alice Vance'],
    ['/agents', 'Connect an agent'],
    ['/explore', 'Explore'],
    ['/nope', 'Page not found'],
    ['/decisions/a/b', 'Page not found'],
  ])('%s -> %s', (path, title) => expect(pageTitleForPath(path)).toBe(title));
});
