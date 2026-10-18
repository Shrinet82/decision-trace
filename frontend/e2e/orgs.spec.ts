import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'path';
import fs from 'fs';

const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
const switcher = (page: Page) => page.getByRole('button', { name: /switch organization/i });

async function expectNoSeriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(
    serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)
  ).toEqual([]);
}

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

async function createOrg(page: Page, name: string) {
  await switcher(page).click();
  await page.getByRole('button', { name: 'New organization' }).click();
  const dialog = page.getByRole('dialog', { name: 'New organization' });
  await dialog.getByLabel('Name').fill(name);
  await dialog.getByRole('button', { name: 'Create organization' }).click();
}

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test.describe('Organizations', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('the switcher starts on the sample organization', async ({ page }) => {
    await page.goto('/app');
    await expect(switcher(page)).toContainText('Acme Corp (sample)');
    await switcher(page).click();
    await expect(page.getByRole('link', { name: /Acme Corp \(sample\)/ })).toBeVisible();
    await expect(page.getByRole('button', { name: 'New organization' })).toBeVisible();
    // The sample cannot be managed or deleted
    await expect(page.getByRole('button', { name: 'Organization settings' })).toHaveCount(0);
  });

  test('a new organization lands on an empty Home and can be switched away from', async ({ page }) => {
    await page.goto('/app');
    await createOrg(page, 'Acme Labs');
    await expect(page).toHaveURL(/\/app\/o\/acme-labs-[0-9a-f]{6}$/);
    await expect(page.getByRole('heading', { name: 'This brain is empty. Add your first sources.' })).toBeVisible();
    await expect(switcher(page)).toContainText('Acme Labs');

    // Links inside the organization stay inside it
    await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: /Decisions/ }).click();
    await expect(page).toHaveURL(/\/app\/o\/acme-labs-[0-9a-f]{6}\/decisions$/);

    // Back to the sample
    await switcher(page).click();
    await page.getByRole('link', { name: /Acme Corp \(sample\)/ }).click();
    await expect(page).toHaveURL(/\/app$/);
    await expect(page.getByRole('region', { name: 'Needs attention' })).toBeVisible();

    // And the new one is remembered in the menu
    await switcher(page).click();
    await expect(page.getByRole('link', { name: 'Acme Labs' })).toBeVisible();
  });

  test('every page of an empty organization renders without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto('/app');
    await createOrg(page, 'Empty Co');
    await expect(page).toHaveURL(/\/app\/o\/empty-co-/);
    const base = new URL(page.url()).pathname;
    for (const section of ['decisions', 'systems', 'people', 'explore', 'sources', 'ask', 'agents']) {
      await page.goto(`${base}/${section}`);
      await expect(page.locator('#main-content')).toBeVisible();
    }
    expect(errors).toEqual([]);
  });

  test('deleting an organization returns to the sample', async ({ page }) => {
    await page.goto('/app');
    await createOrg(page, 'Temp Org');
    await expect(page).toHaveURL(/\/app\/o\/temp-org-/);
    await switcher(page).click();
    await page.getByRole('button', { name: 'Organization settings' }).click();
    const dialog = page.getByRole('dialog', { name: 'Organization settings' });
    await dialog.getByRole('button', { name: 'Delete organization…' }).click();
    await dialog.getByRole('button', { name: /Yes, delete/ }).click();
    await expect(page).toHaveURL(/\/app$/);
    await switcher(page).click();
    await expect(page.getByRole('link', { name: 'Temp Org' })).toHaveCount(0);
  });

  for (const width of [1440, 390]) {
    test(`new organization empty state at ${width}px: accessible, no sideways scroll, screenshot`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/app');
      await createOrg(page, 'Acme Labs');
      await expect(page.getByRole('heading', { name: /This brain is empty/ })).toBeVisible();
      await page.waitForTimeout(300);
      await expectNoSeriousViolations(page);
      await expectNoHorizontalScroll(page);
      await page.screenshot({ path: path.join(screenshotsDir, `org-empty-${width}.png`), fullPage: true });
    });
  }
});

test.describe('Owner key and showcase', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('an organization this browser did not create can be viewed but not changed', async ({ page }) => {
    await page.goto('/app/o/someone-else-123abc');
    await expect(page.getByRole('heading', { name: 'This brain is empty. Add your first sources.' })).toBeVisible();
    await expect(page.getByRole('note')).toContainText('only the browser that created it');
    await expect(page.getByRole('button', { name: 'Upload files' })).toBeHidden();
    await switcher(page).click();
    await page.getByRole('button', { name: 'Organization settings' }).click();
    const dialog = page.getByRole('dialog', { name: 'Organization settings' });
    await expect(dialog.getByRole('note')).toContainText('owner key');
    await expect(dialog.getByRole('button', { name: 'Delete organization…' })).toHaveCount(0);
  });

  test('the organization this browser created keeps its owner key and can add sources', async ({ page }) => {
    await page.goto('/app');
    await createOrg(page, 'Mine');
    const stored = await page.evaluate(() => JSON.parse(window.localStorage.getItem('dt.orgs.v1') ?? '[]'));
    expect(stored[0].owner_key).toMatch(/^ok_/);
    await expect(page.getByRole('button', { name: /Upload files/ })).toBeVisible();
  });

  test('the Arachne showcase organization is listed below Acme and opens read-only with its data', async ({ page }) => {
    await page.goto('/app');
    await switcher(page).click();
    const group = page.getByRole('group', { name: 'Organizations' });
    const names = await group.getByRole('link').allTextContents();
    expect(names[0]).toContain('Acme Corp (sample)');
    expect(names[1]).toContain('Arachne (real GitHub ADRs)');
    await group.getByRole('link', { name: /Arachne/ }).click();
    await expect(page).toHaveURL(/\/app\/o\/arachne$/);
    await expect(switcher(page)).toContainText('Arachne (real GitHub ADRs)');
    // A showcase organization has no settings or delete, and GitHub import is closed like in Acme
    await switcher(page).click();
    await expect(page.getByRole('button', { name: 'Organization settings' })).toHaveCount(0);
  });
});
