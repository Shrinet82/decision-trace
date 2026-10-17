import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'path';
import fs from 'fs';

/**
 * Phase 3 against the mock build (port 4173 => USE_MOCKS). Ask answers replay /ask/stream event
 * streams recorded from the live API (src/mocks/ask-stream.json), waiting each step's recorded
 * time (scaled), so they arrive step by step like the real thing.
 */
const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
const KEYCLOAK_Q = 'Why did we move sessions to Keycloak?';
const IMPACT_Q = "What's affected if we drop Snowflake?";
const EXPERT_Q = 'Who knows the most about Kafka?';
const CONFLICT_Q = 'Do any decisions conflict?';
const OWNER_Q = 'Which systems have no owner?';

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

async function suggested(page: Page, question: string) {
  await page.getByRole('list', { name: 'Suggested questions' }).getByRole('button', { name: question }).click();
}

/** The desktop trace lives in the side panel; on phones it is a disclosure above the answer. */
function trace(page: Page) {
  return page.getByRole('complementary', { name: 'Decision properties' }).getByRole('region', { name: 'How I found this' });
}

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test.describe('streamed Ask', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
  });

  test('steps stream in with times, then the answer, evidence path and total', async ({ page }) => {
    await suggested(page, KEYCLOAK_Q);
    // Steps arrive one at a time: one is running before the answer exists
    const t = trace(page);
    await expect(t.locator('[data-ask-step][data-step-status="running"]').first()).toBeVisible();
    await expect(t.locator('[data-ask-step="understanding"]')).toHaveAttribute('data-step-status', 'done');
    await expect(t.getByTestId('ask-total-ms')).toHaveText(/\d/);
    for (const step of ['understanding', 'matching', 'traversal', 'health', 'composing']) {
      await expect(t.locator(`[data-ask-step="${step}"]`)).toHaveAttribute('data-step-status', 'done');
      await expect(t.locator(`[data-ask-step="${step}"]`)).toContainText(/\d+(\.\d)? (ms|s)/);
    }
    // Matched entities are chips linking to their pages
    const entities = t.getByRole('list', { name: 'Matched entities' });
    await expect(entities.getByRole('link', { name: /Keycloak/ }).first()).toHaveAttribute('href', '/systems/Keycloak');
    // Each Cypher query is collapsible and shows its row count
    const query = t.getByRole('list', { name: 'Cypher queries' }).last().locator('details').first();
    await expect(query.locator('summary')).toContainText(/\d+ rows?/);
    await query.locator('summary').click();
    await expect(query.locator('pre')).toContainText('MATCH');

    const evidence = page.getByRole('region', { name: 'Evidence path' });
    await expect(evidence).toBeVisible();
    await expect(evidence.getByRole('link', { name: /DEC-11/ }).first()).toBeVisible();
    await expect(page.getByText('Still valid').first()).toBeVisible();
  });

  test('impact answer: grouped sections with links, tickets open in Sources', async ({ page }) => {
    await suggested(page, IMPACT_Q);
    const impact = page.getByRole('region', { name: 'Impact of changing Snowflake' });
    await expect(impact).toBeVisible();
    const decisions = impact.getByRole('region', { name: /^Decisions, / });
    for (const code of ['DEC-03', 'DEC-13', 'DEC-17']) {
      await expect(decisions.getByRole('link', { name: new RegExp(code) })).toHaveAttribute('href', `/decisions/${code}`);
    }
    await expect(impact.getByRole('region', { name: /^People, / }).getByRole('link', { name: 'Fiona Gallagher' })).toBeVisible();
    await expect(impact.getByRole('region', { name: /^Teams & projects, / })).toContainText('Data Platform');
    await impact.getByRole('region', { name: /^Tickets, / }).getByRole('link', { name: 'TICK-103' }).click();
    await expect(page).toHaveURL(/\/sources\?open=ticket%2FTICK-103/);
    await expect(page.getByRole('dialog', { name: 'Source' }).getByTestId('source-doc-text')).toBeVisible();
  });

  test('expertise answer: ranked people with evidence counts', async ({ page }) => {
    await suggested(page, EXPERT_Q);
    const list = page.getByRole('region', { name: 'People ranked by evidence' });
    await expect(list).toBeVisible();
    const first = list.locator('ol > li').first();
    await expect(first).toContainText('Alice Vance');
    await expect(first).toContainText('1 decided · 1 owns · 1 meeting · 1 ticket');
    await expect(page.getByRole('region', { name: 'Evidence path' })).toHaveCount(0);
  });

  test('status answers: conflicts and systems without an owner', async ({ page }) => {
    await suggested(page, CONFLICT_Q);
    const conflicts = page.getByRole('region', { name: /^Conflicts, 2/ });
    await expect(conflicts.getByRole('link', { name: /DEC-04/ })).toBeVisible();
    await expect(conflicts.getByRole('link', { name: /DEC-07/ })).toBeVisible();

    await page.locator('#question-input').fill(OWNER_Q);
    await page.locator('#ask-submit-button').click();
    await expect(page.getByRole('region', { name: /^Owner has left, 1/ }).getByRole('link', { name: 'Elasticsearch' })).toBeVisible();
  });
});

test.describe('Sources page', () => {
  test('counts, type filter, and a source drawer with the quote highlighted', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/sources');
    const counts = page.getByLabel('Source counts');
    await expect(counts).toContainText('80');
    await expect(counts).toContainText('Last ingest');
    await page.getByRole('group', { name: 'Source type' }).getByRole('button', { name: 'Meetings' }).click();
    await expect(page.getByRole('list', { name: 'Sources' }).getByRole('listitem')).toHaveCount(12);
    await page.getByRole('list', { name: 'Sources' }).getByRole('button', { name: /Core Messaging Architecture Sync/ }).click();
    const dialog = page.getByRole('dialog', { name: 'Source' });
    await expect(dialog.locator('mark').first()).toBeVisible();
    await expect(dialog.getByRole('region', { name: 'Linked decisions' })).toContainText('DEC-07');
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
  });
});

test('Add source drawer shows when demo data resets', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/sources');
  await page.getByRole('main').getByRole('button', { name: 'Add source' }).click();
  await expect(page.getByTestId('reset-countdown')).toContainText(/resets automatically|No demo data/);
});

for (const width of [1440, 390]) {
  test.describe(`Phase 3 accessibility and screenshots at ${width}px`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
    });

    for (const [file, question, ready] of [
      ['ask-stream', KEYCLOAK_Q, 'Evidence path'],
      ['ask-impact', IMPACT_Q, 'Impact of changing Snowflake'],
      ['ask-expertise', EXPERT_Q, 'People ranked by evidence'],
    ] as const) {
      test(`${file}`, async ({ page }) => {
        await page.goto('/');
        await suggested(page, question);
        await expect(page.getByRole('region', { name: ready })).toBeVisible();
        await expect(page.getByTestId('ask-total-ms').first()).toHaveText(/\d/);
        if (width < 900) {
          // Open the trace disclosure so the screenshot shows how the answer was found
          await page.locator('details', { hasText: 'How I found this' }).first().locator('summary').first().click();
        }
        await expectNoSeriousViolations(page);
        await expectNoHorizontalScroll(page);
        await page.waitForTimeout(300);
        await page.screenshot({ path: path.join(screenshotsDir, `${file}-${width}.png`), fullPage: true });
      });
    }

    test('sources', async ({ page }) => {
      await page.goto('/sources');
      await expect(page.getByRole('list', { name: 'Sources' })).toBeVisible();
      await expectNoSeriousViolations(page);
      await expectNoHorizontalScroll(page);
      await page.screenshot({ path: path.join(screenshotsDir, `sources-${width}.png`), fullPage: true });
      await page.goto('/sources?open=ticket%2FTICK-105');
      await expect(page.getByRole('dialog', { name: 'Source' }).locator('mark').first()).toBeVisible();
      await expectNoSeriousViolations(page);
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(screenshotsDir, `sources-drawer-${width}.png`) });
    });
  });
}
