import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'path';
import fs from 'fs';

const screenshotsDir = path.resolve(process.cwd(), 'screenshots');
const REDIS_Q = 'What replaced Redis for session storage?';
const PROMETHEUS_Q = 'Who decided to adopt Prometheus?';
const QUANTUM_Q = 'Why did we choose quantum encryption for database backups?';

async function ask(page: Page, question: string) {
  await page.locator('#question-input').fill(question);
  await page.locator('#ask-submit-button').click();
}

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

async function settleGraph(page: Page) {
  await expect(page.getByTestId('graph-canvas')).toBeVisible();
  await page.waitForTimeout(900);
}

test.beforeAll(() => {
  fs.mkdirSync(screenshotsDir, { recursive: true });
});

test.describe('journey', () => {
  test('ask, follow a citation, review the decision, explore the graph, use the palette', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/ask');
    await expect(page.locator('h1')).toHaveText('Ask');

    await ask(page, REDIS_Q);

    // Answer, evidence path, sources, and properties panel
    const evidence = page.getByRole('region', { name: 'Evidence path' });
    await expect(evidence).toBeVisible();
    await expect(evidence.getByText('Decision', { exact: true }).first()).toBeVisible();
    const sources = page.getByRole('region', { name: 'Sources' });
    await expect(sources.getByText('TICK-102').first()).toBeVisible();
    const properties = page.getByRole('complementary', { name: 'Decision properties' });
    await expect(properties.getByText('Validity checks')).toBeVisible();
    await expect(properties.getByText('Decided by')).toBeVisible();

    // Superscript citation moves focus to its source card
    await page.getByRole('link', { name: 'Source 1' }).first().click();
    await expect(page.locator('[id^="cite-0-1"]')).toBeFocused();

    // Follow-up composer stays available
    await expect(page.locator('#question-input')).toHaveAttribute('placeholder', 'Ask a follow-up…');

    // Sidebar: Decisions list, grouped; a conflict opens a red callout
    await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: /Decisions/ }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Decisions' })).toBeVisible();
    const conflicts = page.getByRole('region', { name: /^Conflict, / });
    await expect(conflicts).toBeVisible();
    // A row opens the full decision page
    await conflicts.getByRole('link').first().click();
    await expect(page).toHaveURL(/\/decisions\/DEC-\d{2}$/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Lineage' })).toBeVisible();
    await expect(page.getByText(/^Conflict\./)).toBeVisible();
    const props = page.getByRole('complementary', { name: 'Decision properties' });
    await props.getByText('Show Cypher').click();
    await expect(props.getByText('decision_and_lineage')).toBeVisible();
    // Conflicting decision is one click away
    await props.getByRole('link', { name: /^DEC-\d{2}$/ }).first().click();
    await expect(page).toHaveURL(/\/decisions\/DEC-\d{2}$/);
    await expect(page.getByRole('region', { name: 'System timeline' })).toBeVisible();

    // Views link in the sidebar filters the list
    await page.getByRole('link', { name: /^Superseded\s*\d/ }).click();
    await expect(page.getByRole('region', { name: /^Superseded, / })).toBeVisible();
    await expect(page.getByRole('region', { name: /^Active, / })).toHaveCount(0);

    // Graph: canvas, node-type filter with real counts, expand, copy Cypher, inspector
    await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Explore' }).click();
    await settleGraph(page);
    const decisionFilter = page.getByRole('checkbox', { name: /^Decision/ });
    await expect(decisionFilter).toBeChecked();
    await expect(page.getByLabel(/^Ticket/)).toBeVisible();
    await page.getByRole('button', { name: 'Expand' }).click();
    await expect(page.getByText('2 hops')).toBeVisible();
    await page.getByLabel(/^Ticket/).uncheck();
    await expect(page).toHaveURL(/hide=Ticket/);
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.getByRole('button', { name: 'Copy Cypher' }).click();
    await expect(page.getByRole('button', { name: 'Copied' })).toBeVisible();
    const cypher = await page.evaluate(() => navigator.clipboard.readText());
    expect(cypher).toMatch(/^MATCH p = \(n:Decision \{id: 'dec_[0-9a-f]+'\}\)-\[\*1\.\.2\]-\(\) RETURN p$/);
    const inspector = page.getByRole('complementary', { name: 'Selected node' });
    await expect(inspector.getByRole('link', { name: 'Ask about this' })).toBeVisible();
    await expect(inspector.getByRole('link', { name: 'Open decision page' })).toBeVisible();

    // Command palette: filter decisions and jump to one
    await page.keyboard.press('Control+k');
    const dialog = page.getByRole('dialog', { name: 'Search decisions' });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('combobox').fill('keycloak');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/decisions\/DEC-\d{2}$/);
    await expect(dialog).toBeHidden();
  });

  test('orphaned system and its departed owner', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/app');
    await page.getByRole('link', { name: /^Orphaned systems\s*1/ }).click();
    await expect(page).toHaveURL(/\/systems\?view=orphaned/);
    await page.getByRole('link', { name: /Elasticsearch/ }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Elasticsearch' })).toBeVisible();
    await expect(page.getByText('No active owner')).toBeVisible();
    const props = page.getByRole('complementary', { name: 'System properties' });
    await props.getByRole('link', { name: /Marcus Aurelius/ }).click();
    await expect(page).toHaveURL(/\/people\/Marcus%20Aurelius$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Marcus Aurelius' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Systems owned' }).getByText('Orphaned')).toBeVisible();
  });

  test('old /graph links redirect to /explore', async ({ page }) => {
    await page.goto('/graph?node=dec_x');
    await expect(page).toHaveURL(/\/explore\?node=dec_x$/);
  });

  test('unanswerable question shows the empty state with no evidence or citations', async ({
    page,
  }) => {
    await page.goto('/ask');
    await ask(page, QUANTUM_Q);
    await expect(page.getByRole('heading', { name: 'No decision found' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Evidence path' })).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Sources' })).toHaveCount(0);
  });
});

for (const width of [1440, 390]) {
  test.describe(`accessibility and layout at ${width}px`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
    });

    test('Ask page (answer)', async ({ page }) => {
      await page.goto('/ask');
      await expectNoSeriousViolations(page);
      await ask(page, REDIS_Q);
      await expect(page.getByRole('region', { name: 'Evidence path' })).toBeVisible();
      await expectNoSeriousViolations(page);
      await expectNoHorizontalScroll(page);
    });

    test('Ask page (not found)', async ({ page }) => {
      await page.goto('/ask');
      await ask(page, QUANTUM_Q);
      await expect(page.getByRole('heading', { name: 'No decision found' })).toBeVisible();
      await expectNoSeriousViolations(page);
    });

    test('Decisions page', async ({ page }) => {
      await page.goto('/decisions');
      await expect(page.getByRole('region', { name: /^Conflict, / })).toBeVisible();
      await expectNoSeriousViolations(page);
      await expectNoHorizontalScroll(page);
    });

    for (const [label, url, ready] of [
      ['Decision page DEC-11', '/decisions/DEC-11', 'Lineage'],
      ['Decision page DEC-04', '/decisions/DEC-04', 'Lineage'],
      ['System page', '/systems/Elasticsearch', 'Decisions'],
      ['Person page', '/people/Alice%20Vance', 'Decisions made'],
    ] as const) {
      test(label, async ({ page }) => {
        await page.goto(url);
        await expect(page.getByRole('region', { name: ready })).toBeVisible();
        await page.waitForTimeout(600);
        await expectNoSeriousViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }

    test('Systems and People lists', async ({ page }) => {
      await page.goto('/systems');
      await expect(page.getByRole('link', { name: /Elasticsearch/ })).toBeVisible();
      await expectNoSeriousViolations(page);
      await expectNoHorizontalScroll(page);
      await page.goto('/people');
      await expect(page.getByRole('link', { name: /Alice Vance/ })).toBeVisible();
      await expectNoSeriousViolations(page);
      await expectNoHorizontalScroll(page);
    });

    test('Explore page', async ({ page }) => {
      await page.goto('/explore');
      await settleGraph(page);
      await expectNoSeriousViolations(page);
      await expectNoHorizontalScroll(page);
    });

    test('command palette', async ({ page }) => {
      await page.goto('/decisions');
      await expect(page.getByRole('region', { name: /^Conflict, / })).toBeVisible();
      await page.keyboard.press('Control+k');
      await expect(page.getByRole('dialog', { name: 'Search decisions' })).toBeVisible();
      await expectNoSeriousViolations(page);
    });
  });
}

test.describe('screenshots', () => {
  for (const width of [1440, 390]) {
    test(`all pages at ${width}px`, async ({ page }) => {
      test.setTimeout(90000);
      await page.setViewportSize({ width, height: 900 });

      await page.goto('/ask');
      await ask(page, PROMETHEUS_Q);
      await expect(page.getByRole('region', { name: 'Evidence path' })).toBeVisible();
      await expect(page.getByRole('complementary', { name: 'Decision properties' }).getByText('Validity checks')).toBeVisible();
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(screenshotsDir, `ask-${width}.png`), fullPage: true });

      await ask(page, QUANTUM_Q);
      await expect(page.getByRole('heading', { name: 'No decision found' })).toBeVisible();
      await page.waitForTimeout(300);

      await page.goto('/decisions');
      await expect(page.getByRole('region', { name: /^Conflict, / })).toBeVisible();
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(screenshotsDir, `decisions-${width}.png`), fullPage: true });

      await page.goto('/explore');
      await settleGraph(page);
      await page.screenshot({ path: path.join(screenshotsDir, `graph-${width}.png`), fullPage: true });

      for (const [file, url, ready] of [
        ['decision-DEC-11', '/decisions/DEC-11', 'Lineage'],
        ['decision-DEC-04', '/decisions/DEC-04', 'Lineage'],
        ['system-Elasticsearch', '/systems/Elasticsearch', 'Decisions'],
        ['person-Alice-Vance', '/people/Alice%20Vance', 'Decisions made'],
      ] as const) {
        await page.goto(url);
        await expect(page.getByRole('region', { name: ready })).toBeVisible();
        await page.waitForTimeout(900);
        await page.screenshot({ path: path.join(screenshotsDir, `${file}-${width}.png`), fullPage: true });
      }
    });
  }
});
