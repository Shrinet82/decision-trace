/**
 * First-time-judge walkthrough against the live site, in a fresh browser at 1440 and 390 px:
 * Home -> suggested question -> evidence -> decision -> system -> person -> Sources -> Add source
 * (preset A, preset B) -> reset -> Explore -> Agents. Records how long each step took, console
 * errors, failed requests and horizontal overflow, and saves a screenshot of every page.
 *
 * Usage: node scripts/live_walkthrough.mjs [outDir] [--no-ingest]
 * Needs the Playwright browsers installed (frontend/node_modules/playwright-core).
 */
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const SITE = process.env.SITE ?? 'https://decision-trace.pages.dev';
const out = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : 'walkthrough';
const withIngest = !process.argv.includes('--no-ingest');
fs.mkdirSync(out, { recursive: true });

const report = [];
const browser = await chromium.launch();

for (const width of [1440, 390]) {
  // Ingest and reset are limited to 3 a minute per address: let the first run's window pass
  if (withIngest && width === 390) await new Promise((r) => setTimeout(r, 65000));
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await context.newPage();
  const problems = [];
  page.on('console', (m) => m.type() === 'error' && problems.push(`console: ${m.text().slice(0, 160)}`));
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));
  page.on('response', (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(SITE, '')}`));
  page.on('requestfailed', (r) => problems.push(`failed: ${r.url().replace(SITE, '')} ${r.failure()?.errorText}`));

  const steps = [];
  const shot = (name) => page.screenshot({ path: path.join(out, `${name}-${width}.png`), fullPage: true });
  async function step(name, fn) {
    const t = performance.now();
    let error = null;
    try {
      await fn();
    } catch (e) {
      error = e.message.split('\n')[0].slice(0, 200);
      await page.screenshot({ path: path.join(out, `FAILED-${name.replace(/[^a-z0-9]+/gi, '-')}-${width}.png`) }).catch(() => undefined);
    }
    const ms = Math.round(performance.now() - t);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth).catch(() => 0);
    steps.push({ name, ms, error, overflow, url: page.url().replace(SITE, '') || '/' });
  }

  await step('home', async () => {
    await page.goto(SITE);
    await page.getByRole('region', { name: 'Needs attention' }).getByRole('link').first().waitFor();
    await page.getByRole('region', { name: 'Recent changes' }).waitFor();
    await shot('home');
  });
  await step('ask: suggested question', async () => {
    await page.getByRole('button', { name: 'Why did we move sessions to Keycloak?' }).click();
    await page.getByRole('region', { name: 'Evidence path' }).waitFor({ timeout: 30000 });
    await page.getByRole('region', { name: 'Sources' }).waitFor({ timeout: 30000 });
    await shot('ask');
  });
  await step('decision page', async () => {
    await page.locator('main a[href^="/decisions/DEC-"]:visible').first().click();
    await page.getByRole('heading', { level: 1 }).first().waitFor();
    await page.waitForLoadState('networkidle');
    await shot('decision');
  });
  await step('system page', async () => {
    await page.locator('main a[href^="/systems/"]:visible').first().click();
    await page.getByRole('heading', { level: 1 }).first().waitFor();
    await page.waitForLoadState('networkidle');
    await shot('system');
  });
  await step('person page', async () => {
    await page.locator('main a[href^="/people/"]:visible').first().click();
    await page.getByRole('heading', { level: 1 }).first().waitFor();
    await page.waitForLoadState('networkidle');
    await shot('person');
  });
  await step('sources', async () => {
    await page.getByRole('link', { name: /^Sources/ }).first().click();
    await page.getByRole('heading', { level: 1, name: 'Sources' }).waitFor();
    await page.waitForLoadState('networkidle');
    await shot('sources');
  });
  if (withIngest) {
    const drawer = page.getByRole('dialog', { name: 'Add source' });
    await step('add source: open drawer', async () => {
      await page.getByRole('main').getByRole('button', { name: 'Add source' }).click();
      await drawer.waitFor();
      await shot('add-source');
    });
    await step('add source: preset A (Kafka) runs to a diff', async () => {
      await drawer.getByRole('button', { name: 'Arch sync: standardise on Kafka' }).click();
      await drawer.getByRole('button', { name: 'Run', exact: true }).click();
      await drawer.getByRole('region', { name: 'Ingest result' }).waitFor({ timeout: 120000 });
      await page.waitForTimeout(800);
      await shot('ingest-a');
    });
    await step('add source: preset B (Alice leaves) runs to a diff', async () => {
      await drawer.getByRole('button', { name: 'Add another source' }).click();
      await drawer.getByRole('button', { name: 'HR: Alice Vance leaves' }).click();
      await drawer.getByRole('button', { name: 'Run', exact: true }).click();
      await drawer.getByRole('region', { name: 'Ingest result' }).waitFor({ timeout: 120000 });
      await page.waitForTimeout(800);
      await shot('ingest-b');
    });
    await step('reset demo data', async () => {
      await drawer.getByRole('button', { name: 'Reset demo data' }).click();
      await drawer.getByRole('button', { name: 'Reset', exact: true }).click();
      await drawer.getByText(/Reset complete/).waitFor({ timeout: 60000 });
      await page.keyboard.press('Escape');
    });
  }
  await step('explore', async () => {
    await page.getByRole('link', { name: /^Explore/ }).first().click();
    await page.getByTestId('graph-canvas').waitFor();
    await page.waitForTimeout(1200);
    await shot('explore');
  });
  await step('agents', async () => {
    await page.getByRole('link', { name: /^Agents/ }).first().click();
    await page.getByRole('heading', { level: 1, name: 'Connect an agent' }).waitFor();
    await shot('agents');
  });
  for (const [name, route, heading] of [
    ['decisions list', '/decisions', 'Decisions'],
    ['systems list', '/systems', 'Systems'],
    ['people list', '/people', 'People'],
    ['not found', '/no-such-page', 'Page not found'],
  ]) {
    await step(name, async () => {
      await page.goto(SITE + route);
      await page.getByRole('heading', { level: 1, name: heading }).waitFor();
      await page.waitForLoadState('networkidle');
      await shot(name.replace(/ /g, '-'));
    });
  }
  report.push({ width, steps, problems: [...new Set(problems)] });
  await context.close();
}
await browser.close();

for (const r of report) {
  console.log(`\n=== ${r.width}px ===`);
  for (const s of r.steps) {
    const flags = [s.error && `FAILED: ${s.error}`, s.ms > 3000 && 'SLOW', s.overflow > 0 && `OVERFLOW ${s.overflow}px`].filter(Boolean);
    console.log(`${String(s.ms).padStart(6)} ms  ${s.name.padEnd(52)} ${s.url} ${flags.join(' ')}`);
  }
  console.log('problems:', r.problems.length ? r.problems : 'none');
}
fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 1));
process.exit(report.some((r) => r.steps.some((s) => s.error)) ? 1 : 0);
