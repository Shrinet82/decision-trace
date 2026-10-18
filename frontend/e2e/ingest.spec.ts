import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'path';
import fs from 'fs';

/**
 * Live ingest against the mock build (port 4173 => USE_MOCKS). The mock stream replays
 * src/mocks/ingest-*.json, one event every 350 ms, so a full run takes about 6-7 seconds.
 */
const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
const RUN_TIMEOUT = 20000;

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

test.describe('live ingest', () => {
  test('add a source, watch it run, read the diff, then reset', async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/decisions');
    await expect(page.getByRole('region', { name: /^Conflict, / })).toBeVisible();

    // Open the drawer from the top bar
    const trigger = page.getByRole('main').getByRole('button', { name: 'Add source' });
    await trigger.click();
    const drawer = page.getByRole('dialog', { name: 'Add source' });
    await expect(drawer).toBeVisible();

    // Escape closes it and focus returns to the trigger
    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await expect(drawer).toBeVisible();

    // Preset (a) fills the form
    await drawer.getByRole('button', { name: 'Arch sync: standardise on Kafka' }).click();
    await expect(drawer.getByLabel('Title')).toHaveValue('Architecture sync');
    await expect(drawer.getByLabel('Date')).toHaveValue('2026-10-16');
    await drawer.getByRole('button', { name: 'Run', exact: true }).click();

    // A step is running: capture it
    await expect(drawer.locator('[data-step-status="running"]').first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, 'ingest-running-1440.png') });

    // The diff card arrives
    const result = drawer.getByRole('region', { name: 'Ingest result' });
    await expect(result).toBeVisible({ timeout: RUN_TIMEOUT });
    await expect(result.getByText('1 new decision · 2 status changes · conflict resolved')).toBeVisible();
    await expect(
      result.getByRole('region', { name: 'New decisions' }).getByRole('link', { name: 'DEC-18' })
    ).toHaveAttribute('href', '/app/decisions/DEC-18');
    await expect(drawer.locator('[data-step-status="done"]')).toHaveCount(7);
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(screenshotsDir, 'ingest-diff-1440.png') });

    // Accessibility with the drawer open
    await expectNoSeriousViolations(page);

    // Phone width
    await page.setViewportSize({ width: 390, height: 900 });
    await expect(result).toBeVisible();
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(screenshotsDir, 'ingest-diff-390.png') });
    await expectNoSeriousViolations(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    // A diff link opens the decision, closes the drawer, and the page shows the marker
    await result
      .getByRole('region', { name: 'Status changes' })
      .getByRole('link', { name: 'DEC-07' })
      .click();
    await expect(page).toHaveURL(/\/decisions\/DEC-07$/);
    await expect(drawer).toBeHidden();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByText('Changed just now').first()).toBeVisible();

    // The drawer keeps its result; start another source with preset (b)
    await page.getByRole('main').getByRole('button', { name: 'Add source' }).click();
    await expect(drawer).toBeVisible();
    await drawer.getByRole('button', { name: 'Add another source' }).click();
    await drawer.getByRole('button', { name: 'HR: Alice Vance leaves' }).click();
    await expect(drawer.getByLabel('Type')).toHaveValue('announcement');
    await drawer.getByRole('button', { name: 'Run', exact: true }).click();
    const people = drawer.getByRole('region', { name: 'People' });
    await expect(people).toBeVisible({ timeout: RUN_TIMEOUT });
    await expect(people.getByRole('link', { name: 'Alice Vance' })).toBeVisible();
    await expect(people).toContainText('active → left company');
    await expect(drawer.getByRole('region', { name: 'Orphaned systems' })).toContainText('Kafka');

    // Reset demo data, with an inline confirmation
    await drawer.getByRole('button', { name: 'Reset demo data' }).click();
    await expect(drawer.getByText('This removes all demo-ingested data.')).toBeVisible();
    await drawer.getByRole('button', { name: 'Reset', exact: true }).click();
    await expect(drawer.getByText(/Reset complete\. Removed \d+ nodes and \d+ edges/)).toBeVisible();
    await expect(drawer.getByRole('button', { name: 'Run', exact: true })).toBeVisible();
  });
});
