import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'path';

const screenshotsDir = path.resolve(process.cwd(), 'screenshots');

async function expectNoSeriousViolations(page: import('@playwright/test').Page) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([]);
}

test.describe('pages that do not exist say so and offer a way out', () => {
  for (const width of [1440, 390]) {
    test(`unknown address, decision, system and person at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });

      await page.goto('/no-such-page');
      await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible();
      await expect(page).toHaveTitle(/Page not found · Decision Trace/);
      await expectNoSeriousViolations(page);
      await page.screenshot({ path: path.join(screenshotsDir, `not-found-${width}.png`) });
      await page.getByRole('link', { name: 'Go to Home' }).click();
      await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible();

      await page.goto('/decisions/DEC-99');
      await expect(page.getByRole('heading', { level: 1, name: 'Decision not found' })).toBeVisible();
      await expect(page.getByText(/There is no decision DEC-99/)).toBeVisible();
      await expect(page.getByRole('link', { name: 'All decisions' })).toBeVisible();

      await page.goto('/systems/Nope');
      await expect(page.getByRole('heading', { level: 1, name: 'System not found' })).toBeVisible();
      await expect(page.getByRole('link', { name: 'All systems' })).toBeVisible();

      await page.goto('/people/Nobody%20Here');
      await expect(page.getByRole('heading', { level: 1, name: 'Person not found' })).toBeVisible();
      await expect(page.getByRole('link', { name: 'All people' })).toBeVisible();
      await expectNoSeriousViolations(page);
    });
  }
});

test('every page sets its own browser tab title', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const titles: [string, RegExp][] = [
    ['/', /^Decision Trace · Why did we decide that\?$/],
    ['/ask', /^Ask · Decision Trace$/],
    ['/decisions', /^Decisions · Decision Trace$/],
    ['/decisions/DEC-11', /^DEC-11 · Decision Trace$/],
    ['/systems/Elasticsearch', /^Elasticsearch · Decision Trace$/],
    ['/people/Alice%20Vance', /^Alice Vance · Decision Trace$/],
    ['/sources', /^Sources · Decision Trace$/],
    ['/explore', /^Explore · Decision Trace$/],
    ['/agents', /^Connect an agent · Decision Trace$/],
  ];
  for (const [url, title] of titles) {
    await page.goto(url);
    await expect(page).toHaveTitle(title);
  }
});

test('first impression: favicon and social preview tags', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/favicon.svg');
  const og = (p: string) => page.locator(`meta[property="${p}"]`).getAttribute('content');
  expect(await og('og:title')).toContain('Decision Trace');
  expect(await og('og:image')).toBe('https://decision-trace.pages.dev/og.png');
  expect(await og('og:image:width')).toBe('1200');
  await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute('content', 'summary_large_image');
  const png = await page.request.get('/og.png');
  expect(png.ok()).toBeTruthy();
});

test('search with no matches says so and offers to ask instead', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible();
  await page.getByRole('button', { name: /^Search/ }).click();
  await page.getByRole('combobox').fill('zzzqqq');
  await expect(page.getByText('No decisions, systems or people match.')).toBeVisible();
  await expect(page.getByRole('option', { name: /Ask: “zzzqqq”/ })).toBeVisible();
});
