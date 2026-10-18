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

test.describe('Company map', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('Explore opens the whole map with tickets hidden, and the filters change it', async ({ page }) => {
    await page.goto('/app/explore');
    await expect(page.getByRole('heading', { name: 'Company map' })).toBeVisible();
    await expect(page.getByTestId('company-map')).toBeVisible();
    await expect(page.getByRole('checkbox', { name: /^Ticket/ })).not.toBeChecked();
    await expect(page.getByRole('checkbox', { name: /^Decision/ })).toBeChecked();
    await expect(page.getByText(/Showing 66 of 146 nodes/)).toBeVisible();
    const legend = page.getByRole('list', { name: 'Legend' });
    await expect(legend).toContainText('Decision');
    await expect(legend).toContainText('Conflict');

    await page.getByRole('checkbox', { name: /^Ticket/ }).check();
    await expect(page.getByText(/Showing 146 of 146 nodes/)).toBeVisible();
    await page.getByLabel('Health overlay').uncheck();
    await expect(legend).not.toContainText('Conflict');
  });

  test('search finds a node and shows its details; Focus and Map switch views', async ({ page }) => {
    await page.goto('/app/explore');
    await page.getByLabel('Find a node').fill('kafka');
    const results = page.getByRole('list', { name: 'Matching nodes' });
    await expect(results.getByRole('button').first()).toBeVisible();
    await results.getByRole('button').first().click();
    const inspector = page.getByRole('complementary', { name: 'Selected node' });
    await expect(inspector.getByRole('heading', { level: 2 })).toBeVisible();
    await page.getByRole('button', { name: 'Focus', exact: true }).click();
    await expect(page).toHaveURL(/node=/);
    await expect(page.getByRole('button', { name: 'Expand' })).toBeVisible();
    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await expect(page).not.toHaveURL(/node=/);
    await expect(page.getByTestId('company-map')).toBeVisible();
  });

  test('an organization with nothing in it shows an empty map message', async ({ page }) => {
    await page.goto('/app/o/acme-labs-3f9a1c/explore');
    await expect(page.getByRole('heading', { name: 'The map is empty' })).toBeVisible();
  });

  for (const width of [1440, 390]) {
    test(`map at ${width}px: accessible, screenshot`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/app/explore');
      await expect(page.getByTestId('company-map')).toBeVisible();
      await page.waitForTimeout(1200);
      await expectNoSeriousViolations(page);
      await page.screenshot({ path: path.join(screenshotsDir, `map-${width}.png`) });
    });
  }
});
