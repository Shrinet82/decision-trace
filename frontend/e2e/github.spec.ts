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

test.describe('GitHub import', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('the sample organization explains that import needs your own organization', async ({ page }) => {
    await page.goto('/app');
    await page.getByRole('button', { name: 'Try adding a source' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add source' });
    await dialog.getByRole('tab', { name: 'GitHub' }).click();
    await expect(dialog.getByRole('note')).toContainText('organizations you create');
    await expect(dialog.getByLabel('Repository URL')).toBeDisabled();
    await expect(dialog.getByRole('button', { name: 'Import' })).toBeDisabled();
  });

  test('import a repository: steps, then the decisions it found', async ({ page }) => {
    await page.goto('/app/o/acme-labs-3f9a1c');
    await page.getByRole('button', { name: /Import from GitHub/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Add source' });
    await expect(dialog.getByRole('tab', { name: 'GitHub', selected: true })).toBeVisible();
    const url = dialog.getByLabel('Repository URL');
    await url.fill('not a url');
    await expect(dialog.getByRole('button', { name: 'Import' })).toBeDisabled();
    await url.fill('https://github.com/owner/repo');
    await dialog.getByRole('button', { name: 'Import' }).click();
    const result = dialog.getByRole('region', { name: 'Result', exact: true });
    await expect(result).toBeVisible();
    await expect(dialog.getByTestId('import-stats')).toContainText('12 ADRs');
    await expect(dialog.getByRole('list', { name: 'Import steps' }).locator('[data-step-status="done"]')).toHaveCount(5);
  });

  test('a repository that is not found shows the reason and a way back', async ({ page }) => {
    await page.goto('/app/o/acme-labs-3f9a1c');
    await page.getByRole('button', { name: /Import from GitHub/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Add source' });
    await dialog.getByLabel('Repository URL').fill('https://github.com/owner/nope');
    await dialog.getByRole('button', { name: 'Import' }).click();
    await expect(dialog.getByRole('alert')).toContainText('not found');
    await dialog.getByRole('button', { name: 'Back' }).click();
    await expect(dialog.getByLabel('Repository URL')).toBeVisible();
  });

  for (const width of [1440, 390]) {
    test(`GitHub tab at ${width}px: accessible, screenshot`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/app/o/acme-labs-3f9a1c');
      await page.getByRole('button', { name: /Import from GitHub/ }).click();
      const dialog = page.getByRole('dialog', { name: 'Add source' });
      await dialog.getByLabel('Repository URL').fill('https://github.com/owner/repo');
      await page.waitForTimeout(300);
      await expectNoSeriousViolations(page);
      await page.screenshot({ path: path.join(screenshotsDir, `github-${width}.png`) });
    });
  }
});
