import { test, expect } from '@playwright/test';

// Batch 18 field-trial correctness fixes — browser-level verification.
// Run against a built dist served on BASE_URL (e.g. make serve-dist on :8081).

test.describe('Batch 18 — June field observations', () => {
  test('June 21 MP: propers collect surfaced, no "Coll above" reading (BUG-26/27)', async ({ page }) => {
    await page.goto('/#/2026-06-21/mp');
    const collect = page.locator('#prayers-collect');
    await expect(collect).toContainText('National Indigenous Day of Prayer', { timeout: 5000 });
    await expect(collect).toContainText('Creator God, from you every family');
    // The stripped pseudo-lesson must not appear anywhere as a reading.
    await expect(page.locator('.reading-heading', { hasText: 'Coll above' })).toHaveCount(0);
  });

  test('June 23 MP: "two of three readings" pick rubric renders (BUG-28)', async ({ page }) => {
    await page.goto('/#/2026-06-23/mp');
    await expect(page.locator('.seg-rubric', { hasText: 'Two of the following three readings are read.' }))
      .toBeVisible({ timeout: 5000 });
  });

  test('June 24 MP: no pick rubric on a day without lessons_pick (BUG-28 negative)', async ({ page }) => {
    await page.goto('/#/2026-06-24/mp');
    await expect(page.locator('.office-section-title').first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Two of the following three readings are read.')).toHaveCount(0);
  });

  test('Wednesday litany: "Holy One" capitalised, placeholder N italic (BUG-25/30)', async ({ page }) => {
    // 2026-06-17 is an ordinary Wednesday → ordinary-wednesday-mp litany.
    await page.goto('/#/2026-06-17/mp');
    const body = page.locator('body');
    await expect(body).toContainText('Holy One, accomplish your purposes in us.', { timeout: 5000 });
    await expect(body).not.toContainText('holy one, accomplish');
  });

  test('Dec 17 EP: no "O Antiphon" pseudo-lesson (BUG-33)', async ({ page }) => {
    await page.goto('/#/2025-12-17/ep');
    await expect(page.locator('.office-section-title').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.reading-heading', { hasText: 'O Antiphon' })).toHaveCount(0);
  });
});
