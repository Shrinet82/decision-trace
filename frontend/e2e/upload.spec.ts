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

const ORG = '/app/o/acme-labs-3f9a1c';

async function openUpload(page: Page) {
  await page.goto(ORG);
  await page.getByRole('button', { name: /Upload files/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Add source' });
  await expect(dialog.getByRole('tab', { name: 'Upload files', selected: true })).toBeVisible();
  return dialog;
}

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test.describe('File upload', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('pick files, set a type, ingest, read the combined result', async ({ page }) => {
    const dialog = await openUpload(page);
    await dialog.getByLabel('Choose files to upload').setInputFiles([
      { name: 'adr-0001-kafka.md', mimeType: 'text/markdown', buffer: Buffer.from('# ADR-0001\nStatus: Accepted\n## Decision\nWe use Kafka.') },
      { name: 'sync-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Attendees: Alice Vance, Bob Martin\nWe decided to use Kafka.') },
      { name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from('x') },
    ]);
    const list = dialog.getByRole('list', { name: 'Files to upload' });
    await expect(list.getByRole('listitem')).toHaveCount(3);
    await expect(list.getByText('Only .md, .txt and .pdf files are supported.')).toBeVisible();
    await list.getByLabel('Document type for adr-0001-kafka.md').selectOption('adr');

    await dialog.getByRole('button', { name: 'Ingest 2 files' }).click();
    const progress = dialog.getByRole('list', { name: 'Upload progress' });
    await expect(progress.getByRole('listitem')).toHaveCount(2);
    const result = dialog.getByRole('region', { name: 'Result' });
    await expect(result).toBeVisible();
    await expect(progress.locator('[data-file-status="done"]')).toHaveCount(2);
    await expect(dialog.getByRole('button', { name: 'Upload more files' })).toBeVisible();
  });

  test('a file that cannot be read is skipped with its reason, the others still ingest', async ({ page }) => {
    const dialog = await openUpload(page);
    await dialog.getByLabel('Choose files to upload').setInputFiles([
      { name: 'notes.md', mimeType: 'text/markdown', buffer: Buffer.from('We decided to use Kafka.') },
      { name: 'scan.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') },
    ]);
    await dialog.getByRole('button', { name: 'Ingest 2 files' }).click();
    const progress = dialog.getByRole('list', { name: 'Upload progress' });
    await expect(progress.locator('[data-file-status="skipped"]')).toContainText('no extractable text');
    await expect(progress.locator('[data-file-status="done"]')).toHaveCount(1);
  });

  test('at most ten files are accepted', async ({ page }) => {
    const dialog = await openUpload(page);
    const many = Array.from({ length: 12 }, (_, i) => ({ name: `n${i}.md`, mimeType: 'text/markdown', buffer: Buffer.from('We decided X.') }));
    await dialog.getByLabel('Choose files to upload').setInputFiles(many);
    await expect(dialog.getByRole('list', { name: 'Files to upload' }).getByRole('listitem')).toHaveCount(10);
    await expect(dialog.getByText('Only 10 files per upload: 2 not added.')).toBeVisible();
  });

  for (const width of [1440, 390]) {
    test(`upload drawer at ${width}px: accessible, screenshot`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const dialog = await openUpload(page);
      await dialog.getByLabel('Choose files to upload').setInputFiles([
        { name: 'adr-0001-kafka.md', mimeType: 'text/markdown', buffer: Buffer.from('We decided to use Kafka.') },
      ]);
      await expect(dialog.getByRole('list', { name: 'Files to upload' })).toBeVisible();
      await page.waitForTimeout(300);
      await expectNoSeriousViolations(page);
      await page.screenshot({ path: path.join(screenshotsDir, `upload-${width}.png`) });
    });
  }
});
