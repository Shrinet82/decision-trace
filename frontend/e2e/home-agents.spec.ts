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

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test.describe('Home', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('shows real counts, the attention queue and recent changes', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible();

    const stats = page.getByRole('region', { name: 'The brain' });
    await expect(stats.getByText('Decisions', { exact: true })).toBeVisible();
    await expect(stats.locator('dd').first()).toHaveText('17');
    await expect(stats.getByText('146 nodes')).toBeVisible();
    await expect(stats.getByText('374 edges')).toBeVisible();

    const attention = page.getByRole('region', { name: 'Needs attention' });
    await expect(attention.getByRole('link', { name: /DEC-04 and DEC-07 conflict/ })).toBeVisible();
    await expect(attention.getByRole('link', { name: /Elasticsearch has no active owner/ })).toBeVisible();
    await expect(attention.getByText(/Marcus Aurelius left on 2025-11-30/)).toBeVisible();

    const changes = page.getByRole('region', { name: 'Recent changes' });
    await expect(changes.getByText(/Agent/).first()).toBeAttached();
    await expect(changes.getByText(/Keycloak/).first()).toBeVisible();
  });

  test('explains what this is, with counts from the API and three things to try', async ({ page }) => {
    await page.goto('/');
    const intro = page.getByRole('region', { name: 'What is this?' });
    await expect(intro.getByText(/80 tickets, 12 meeting notes and 37 records/)).toBeVisible();
    await expect(intro.getByRole('link', { name: 'Why did we move sessions to Keycloak?' })).toBeVisible();
    await expect(intro.getByRole('link', { name: 'Do any decisions conflict?' })).toBeVisible();
    await expect(intro.getByRole('link', { name: 'Explore the decision graph' })).toBeVisible();
    await intro.getByRole('button', { name: 'Try adding a source' }).click();
    await expect(page.getByRole('dialog', { name: /Add source/i })).toBeVisible();
  });

  test('attention rows open the decision or system page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: /DEC-04 and DEC-07 conflict/ }).click();
    await expect(page).toHaveURL(/\/decisions\/DEC-04$/);
    await page.goto('/');
    await page.getByRole('link', { name: /Elasticsearch has no active owner/ }).click();
    await expect(page).toHaveURL(/\/systems\/Elasticsearch$/);
  });

  test('asking from Home opens /ask with the streamed answer', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Why did we move sessions to Keycloak?' }).click();
    // /ask clears ?q= once the question is running
    await expect(page).toHaveURL(/\/ask$/);
    await expect(page.getByRole('region', { name: 'Evidence path' })).toBeVisible();

    await page.goto('/');
    await page.getByLabel('Ask a question').fill('Who decided to adopt Prometheus?');
    await page.getByRole('button', { name: 'Ask', exact: true }).click();
    await expect(page).toHaveURL(/\/ask$/);
    await expect(page.getByText('Who decided to adopt Prometheus?').first()).toBeVisible();
  });

  test('an old /?q= link still lands on the answer', async ({ page }) => {
    await page.goto('/?q=Why%20did%20we%20move%20sessions%20to%20Keycloak%3F');
    await expect(page).toHaveURL(/\/ask/);
    await expect(page.getByRole('region', { name: 'Evidence path' })).toBeVisible();
  });
});

test.describe('Connect an agent', () => {
  test('endpoint, copy button, client snippets and tools', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await page.getByRole('link', { name: 'Agents' }).click();
    await expect(page).toHaveURL(/\/agents$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Connect an agent' })).toBeVisible();

    const connector = page.getByRole('heading', { name: /custom connector \(recommended\)/ });
    const configFile = page.getByRole('heading', { name: /Claude Desktop with a config file/ });
    await expect(connector).toBeVisible();
    await expect(page.getByText('Choose Add custom connector.')).toBeVisible();
    const [a, b] = [await connector.boundingBox(), await configFile.boundingBox()];
    expect(a!.y).toBeLessThan(b!.y);

    const url = await page.getByTestId('mcp-url').innerText();
    expect(url).toMatch(/^https:\/\/.+\/mcp$/);
    await page.getByRole('button', { name: 'Copy endpoint URL' }).click();
    await expect(page.getByRole('button', { name: 'Copy endpoint URL: copied' })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(url);

    await expect(page.getByLabel('Claude Code configuration', { exact: true })).toContainText(
      `claude mcp add --transport http decision-trace ${url}`
    );
    const desktop = await page.getByLabel('Claude Desktop configuration', { exact: true }).innerText();
    expect(JSON.parse(desktop).mcpServers['decision-trace'].args).toEqual([
      '-y', 'mcp-remote', url, '--transport', 'http-only',
    ]);
    const cursor = await page.getByLabel('Cursor configuration', { exact: true }).innerText();
    expect(JSON.parse(cursor)).toEqual({ mcpServers: { 'decision-trace': { url } } });

    const tools = page.getByRole('region', { name: 'Tools' });
    for (const name of ['ask', 'get_decision', 'list_decisions', 'impact_of', 'who_knows', 'find_conflicts', 'add_source']) {
      await expect(tools.getByText(name, { exact: true })).toBeVisible();
    }
    await expect(tools.getByText(/Ask Decision Trace why we use Keycloak/)).toBeVisible();
  });
});

for (const width of [1440, 390]) {
  test.describe(`accessibility, layout and screenshots at ${width}px`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
    });

    for (const [file, route, ready] of [
      ['home', '/', 'Needs attention'],
      ['agents', '/agents', 'Tools'],
    ] as const) {
      test(file, async ({ page }) => {
        await page.goto(route);
        await expect(page.getByRole('region', { name: ready })).toBeVisible();
        await page.waitForTimeout(300);
        await expectNoSeriousViolations(page);
        await expectNoHorizontalScroll(page);
        await page.screenshot({ path: path.join(screenshotsDir, `${file}-${width}.png`), fullPage: true });
      });
    }
  });
}
