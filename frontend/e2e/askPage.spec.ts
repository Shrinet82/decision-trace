import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import path from 'path';
import fs from 'fs';

test.describe('Ask Page and App Shell End-to-End', () => {
  const screenshotsDir = path.resolve(process.cwd(), 'screenshots');

  test.beforeAll(() => {
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test('full user journey: ask question, explore evidence, open drawer, toggle path list, and switch theme', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');

    // Verify header and page structure
    await expect(page.locator('h1')).toHaveText('Ask');
    await expect(page.locator('#question-input')).toBeVisible();

    // Ask a benchmark question using the example question button
    const redisExampleButton = page.getByRole('button', {
      name: 'What replaced Redis for session storage?',
    });
    await expect(redisExampleButton).toBeVisible();
    await redisExampleButton.click();

    // Verify answer renders
    await expect(
      page.getByText('Migrate session storage to embedded Keycloak cache').first()
    ).toBeVisible();

    // Verify people involved
    await expect(page.getByText('Alice Vance', { exact: true }).first()).toBeVisible();

    // Verify sources list
    await expect(page.getByText('TICK-101').first()).toBeVisible();

    // Open source drawer
    const sourceCard = page.locator('button:has-text("TICK-101")').first();
    await sourceCard.click();

    // Verify drawer dialog
    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible();
    await expect(page.getByText('Source details')).toBeVisible();

    // Close drawer
    await page.getByLabel('Close drawer').click();
    await expect(drawer).not.toBeVisible();

    // Toggle "Path as list"
    const toggleListBtn = page.getByRole('button', { name: /Path as list/i });
    await toggleListBtn.click();
    await expect(page.getByRole('button', { name: /Path as graph/i })).toBeVisible();
    await expect(page.locator('#heading-decisions')).toBeVisible();

    // Toggle back to "Path as graph"
    const toggleGraphBtn = page.getByRole('button', { name: /Path as graph/i });
    await toggleGraphBtn.click();
    await expect(page.getByRole('button', { name: /Path as list/i })).toBeVisible();

    // Toggle theme to dark and back
    const themeToggleBtn = page.locator('button[aria-label*="Switch to dark theme"]:visible');
    await themeToggleBtn.click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

    const themeToggleLightBtn = page.locator('button[aria-label*="Switch to light theme"]:visible');
    await themeToggleLightBtn.click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });

  test('automated accessibility check (axe) in light and dark themes (zero serious or critical violations)', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');

    // Ask question so full content and graph are visible
    await page.getByRole('button', {
      name: 'What replaced Redis for session storage?',
    }).click();
    await expect(
      page.getByText('Migrate session storage to embedded Keycloak cache').first()
    ).toBeVisible();

    // Axe check in Light theme
    const lightAxeResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const lightViolations = lightAxeResults.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical'
    );
    expect(lightViolations).toEqual([]);

    // Switch to Dark theme
    await page.locator('button[aria-label*="Switch to dark theme"]:visible').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');

    // Axe check in Dark theme
    const darkAxeResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const darkViolations = darkAxeResults.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical'
    );
    expect(darkViolations).toEqual([]);
  });

  test('captures screenshots of answer and not-found states across 1440, 1024, and 390 widths in light and dark', async ({
    page,
  }) => {
    test.setTimeout(120000);
    const widths = [1440, 1024, 390];
    const themes: ('light' | 'dark')[] = ['light', 'dark'];

    for (const width of widths) {
      for (const theme of themes) {
        // --- 1. Answer State ---
        await page.setViewportSize({ width, height: 900 });
        await page.goto('/');

        // Set theme
        await page.evaluate((t) => {
          document.documentElement.setAttribute('data-theme', t);
          if (t === 'dark') {
            document.documentElement.classList.add('dark');
          } else {
            document.documentElement.classList.remove('dark');
          }
        }, theme);

        // Ask question to reach answer state
        await page.locator('#question-input').fill('What replaced Redis for session storage?');
        await page.locator('#ask-submit-button').click();
        await expect(
          page.getByText('Migrate session storage to embedded Keycloak cache').first()
        ).toBeVisible();

        // Brief delay for stable layout rendering
        await page.waitForTimeout(300);

        await page.screenshot({
          path: path.join(screenshotsDir, `ask-answer-${width}-${theme}.png`),
          fullPage: true,
        });

        // --- 2. Not-Found State ---
        await page.locator('#question-input').fill('Why did we choose quantum encryption for database backups?');
        await page.locator('#ask-submit-button').click();
        await expect(
          page.getByText('No answer found in the indexed tickets, notes, and records.')
        ).toBeVisible();

        await page.waitForTimeout(300);

        await page.screenshot({
          path: path.join(screenshotsDir, `ask-not-found-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    }
  });
});
