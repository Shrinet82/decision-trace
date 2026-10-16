import { test } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { pathToFileURL } from 'url';

/**
 * Renders the static design mockups in design-ref/ and composes each next to the
 * matching implementation screenshot produced by app.spec.ts (which runs first).
 * Output: screenshots/design/<page>-<width>.png and screenshots/compare-<page>-<width>.png
 */
const root = process.cwd();
const designDir = path.join(root, 'design-ref');
const shots = path.join(root, 'screenshots');

const PAGES = [
  { name: 'ask', mock: 'Main.dc.html' },
  { name: 'decisions', mock: 'Decisions.dc.html' },
  { name: 'graph', mock: 'Graph.dc.html' },
];

for (const width of [1440, 390]) {
  for (const { name, mock } of PAGES) {
    test(`compare ${name} at ${width}px`, async ({ page, browser }) => {
      test.setTimeout(60000);
      fs.mkdirSync(path.join(shots, 'design'), { recursive: true });

      await page.setViewportSize({ width, height: 900 });
      await page.goto(pathToFileURL(path.join(designDir, mock)).href);
      await page.waitForTimeout(600);
      const designPath = path.join(shots, 'design', `${name}-${width}.png`);
      await page.screenshot({ path: designPath, fullPage: true });

      const implPath = path.join(shots, `${name}-${width}.png`);
      const b64 = (p: string) => fs.readFileSync(p).toString('base64');
      const context = await browser.newContext({ viewport: { width: width * 2 + 48, height: 900 } });
      const sheet = await context.newPage();
      await sheet.setContent(`
        <body style="margin:0;background:#E6E7EB;font:600 14px system-ui;color:#1B1C1F">
          <div style="display:flex;gap:16px;padding:16px;align-items:flex-start">
            <figure style="margin:0"><figcaption style="padding:0 0 8px">Design reference</figcaption>
              <img style="display:block;width:${width}px;border:1px solid #C9CCD3" src="data:image/png;base64,${b64(designPath)}"></figure>
            <figure style="margin:0"><figcaption style="padding:0 0 8px">Implementation</figcaption>
              <img style="display:block;width:${width}px;border:1px solid #C9CCD3" src="data:image/png;base64,${b64(implPath)}"></figure>
          </div>
        </body>`);
      await sheet.screenshot({
        path: path.join(shots, `compare-${name}-${width}.png`),
        fullPage: true,
      });
      await context.close();
    });
  }
}
