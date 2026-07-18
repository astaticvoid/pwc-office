// @ts-check
import { test, expect } from '@playwright/test';

const DATE = '2026-07-12';
const MP = `/#/${DATE}/mp`;

const VIEWPORTS = [
  { name: 'mobile', width: 320, height: 568 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 800 },
];

test.describe('responsive layout', () => {
  for (const vp of VIEWPORTS) {
    test(`${vp.name} (${vp.width}px) renders without horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(MP, { waitUntil: 'domcontentloaded' });

      // Wait for content to load
      await page.waitForSelector('.office-section-title', { timeout: 15000 });

      // Check for horizontal overflow
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = await page.evaluate(() => window.innerWidth);
      expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 1);
    });

    test(`${vp.name} — all section headings visible`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(MP, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.office-section-title', { timeout: 15000 });

      const headings = await page.locator('.office-section-title').all();
      expect(headings.length).toBeGreaterThanOrEqual(3);
    });

    test(`${vp.name} — alternatives tabs render without clipping`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(MP, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.alt-tab', { timeout: 15000 });

      const tabs = await page.locator('.alt-tab').all();
      for (const tab of tabs) {
        const box = await tab.boundingBox();
        if (box) {
          expect(box.x).toBeGreaterThanOrEqual(0);
          expect(box.x + box.width).toBeLessThanOrEqual(vp.width + 1);
        }
      }
    });
  }
});
