import { test, expect } from '@playwright/test';


test.describe('Offline mode (ADR 0025)', () => {
  test('gracefully loads prefetched days and handles offline misses', async ({ page }) => {
    // Navigate to the app while online
    await page.goto('/');

    // Wait for the app to initialize
    await page.waitForSelector('#day-title', { state: 'visible' });

    // Give the background prefetchRollingWindow time to populate cache
    await page.waitForTimeout(1000);

    // Simulate offline mode by aborting all future API requests
    await page.route('**/api/**', route => route.abort('internetdisconnected'));

    // Force the app to consider itself offline
    await page.evaluate(() => { window.__pwcOffline = true; });

    // Navigate to tomorrow (which should be in the prefetched window)
    const todayStr = await page.evaluate(() => new Date().toISOString().split('T')[0]);
    const d = new Date(todayStr);
    d.setUTCDate(d.getUTCDate() + 1);
    const tomorrowStr = d.toISOString().split('T')[0];

    await page.locator('#nav-cal-btn').click();
    await page.locator('#day-date-picker').fill(tomorrowStr);
    // filling alone triggers the change event in the app, but Playwright fill doesn't always fire change.
    await page.locator('#day-date-picker').press('Enter');
    await page.waitForTimeout(500);

    // Should still be able to render the UI (via cache)
    await expect(page.locator('#day-title')).toBeVisible();

    // Now try to navigate to a day far in the future that is NOT in the 30-day prefetch window (e.g. +60 days)
    const d2 = new Date(todayStr);
    d2.setUTCDate(d2.getUTCDate() + 60);
    const futureStr = d2.toISOString().split('T')[0];

    await page.locator('#nav-cal-btn').click();
    await page.locator('#day-date-picker').fill(futureStr);
    await page.locator('#day-date-picker').press('Enter');

    // It should gracefully surface the offline load error instead of crashing
    await expect(page.locator('.error-msg').first()).toContainText('Network connection required');
  });

  test('settings sheet provides cache purge and copy diagnostics utilities', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#day-title', { state: 'visible' });

    // Open Settings sheet
    await page.locator('#nav-settings-btn').click();
    await expect(page.locator('#settings-sheet')).toHaveAttribute('aria-hidden', 'false');

    // Verify cache status label and buttons are present
    const cacheLabel = page.locator('#cache-status-label');
    await expect(cacheLabel).toBeVisible();

    const clearBtn = page.locator('#clear-cache-btn');
    await expect(clearBtn).toBeVisible();

    const copyBtn = page.locator('#copy-diag-btn');
    await expect(copyBtn).toBeVisible();

    // Click clear cache button
    await clearBtn.click();
    await expect(clearBtn).toContainText(/Cleared!|Clear Cache/);
    await expect(cacheLabel).toHaveText('0 cached days');

    // Click copy diagnostics button
    await copyBtn.click();
    await expect(copyBtn).toContainText(/Copied!|Copy Info/);
  });
});
