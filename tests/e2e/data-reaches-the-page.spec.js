import { test, expect } from '@playwright/test';
import { gotoOffice } from './helpers.js';

// What the data carries reaches the page, and what it does not carry does not
// appear. Each case names a day whose lectionary or office data settles the
// question, then asks the rendered page — the join these tests cover is
// between the data and the DOM, which no unit test spans.
// Run against a built dist served on BASE_URL (e.g. make serve-dist on :8081).

test.describe('the page shows what the data carries', () => {
  test('a collect carried in the day\'s propers reaches the page, its cross-reference does not', async ({ page }) => {
    // 2026-06-21: National Indigenous Day of Prayer, whose propers carry the
    // collect inline and whose office cites it as "Coll above".
    await gotoOffice(page, '2026-06-21', 'mp');
    const collect = page.locator('#prayers-collect');
    await expect(collect).toContainText('National Indigenous Day of Prayer', { timeout: 5000 });
    await expect(collect).toContainText('Creator God, from you every family');
    // The stripped pseudo-lesson must not appear anywhere as a reading.
    await expect(page.locator('.reading-heading', { hasText: 'Coll above' })).toHaveCount(0);
  });

  test('a day offering a choice of readings announces it', async ({ page }) => {
    // The rubric is the fixed form from LITURGICAL_TEXT_REGISTER (ADR 0014/#63),
    // not a per-count computed sentence — same text regardless of pick/total.
    // 2026-06-23 is a day carrying lessons_pick.
    await gotoOffice(page, '2026-06-23', 'mp');
    await expect(page.locator('.seg-rubric', { hasText: 'One or two of the following readings are read.' }))
      .toBeVisible({ timeout: 5000 });
  });

  test('a day offering no choice announces none', async ({ page }) => {
    // 2026-06-24 carries no lessons_pick.
    await gotoOffice(page, '2026-06-24', 'mp');
    await expect(page.locator('.office-section-title').first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('One or two of the following readings are read.')).toHaveCount(0);
  });

  test('the litany divine title reaches the page with its capital (#4)', async ({ page }) => {
    // 2026-06-17 is an ordinary Wednesday → ordinary-wednesday-mp litany.
    await gotoOffice(page, '2026-06-17', 'mp');
    const body = page.locator('body');
    await expect(body).toContainText('Holy One, accomplish your purposes in us.', { timeout: 5000 });
    await expect(body).not.toContainText('holy one, accomplish');
  });
});
