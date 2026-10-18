import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'path';
import fs from 'fs';

const screenshotsDir = path.resolve(process.cwd(), 'screenshots');

async function expectNoSeriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(
    serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)
  ).toEqual([]);
}

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test.describe('Landing and routing', () => {
  test('the root is the landing page, with both calls to action', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Decision Trace/);
    await expect(
      page.getByRole('heading', { level: 1, name: /Ask why any decision was made/ })
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Try the product' }).first()).toHaveAttribute('href', '/app');
    await expect(page.getByRole('link', { name: 'Connect an agent' }).first()).toHaveAttribute('href', '/app/agents');
    await expect(page.getByRole('heading', { name: 'How it works' })).toBeVisible();
  });

  test('Try the product opens the sample organization', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Try the product' }).first().click();
    await expect(page).toHaveURL(/\/app$/);
    await expect(page.getByRole('region', { name: 'Needs attention' })).toBeVisible();
  });

  test('old app addresses redirect under /app', async ({ page }) => {
    await page.goto('/decisions/DEC-11?x=1');
    await expect(page).toHaveURL(/\/app\/decisions\/DEC-11\?x=1$/);
    await page.goto('/graph?node=dec_x');
    await expect(page).toHaveURL(/\/app\/explore\?node=dec_x$/);
    await page.goto('/nonsense');
    await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();
  });

  for (const width of [1440, 390]) {
    test(`landing at ${width}px: accessible, no sideways scroll, screenshot`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');
      await expect(page.getByRole('heading', { name: 'The company map' })).toBeVisible();
      await page.waitForTimeout(300);
      await expectNoSeriousViolations(page);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      );
      expect(overflow).toBeLessThanOrEqual(0);
      await page.screenshot({ path: path.join(screenshotsDir, `landing-${width}.png`), fullPage: true });
    });
  }
});
