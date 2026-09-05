import { test, expect } from '@playwright/test';
import { gotoOffice } from './helpers.js';
import { findDay, dayOf, seasonFor } from './days.js';

// What the data carries reaches the page, and what it does not carry does not
// appear. Each case names a day whose lectionary or office data settles the
// question, then asks the rendered page — the join these tests cover is
// between the data and the DOM, which no unit test spans.
// Run against a built dist served on BASE_URL (e.g. make serve-dist on :8081).

test.describe('the page shows what the data carries', () => {
  test('a collect carried in the day\'s propers reaches the page, its cross-reference does not', async ({ page }) => {
    // A day whose propers carry the collect inline, which its office cites as
    // "Coll above" rather than by page number.
    const date = findDay('a day whose propers carry their collect inline',
      d => d.collect_inline && d.collect_inline.text);
    await gotoOffice(page, date, 'mp');
    const collect = page.locator('#prayers-collect');
    const inline = dayOf(date).collect_inline;
    await expect(collect).toContainText(inline.name, { timeout: 5000 });
    await expect(collect).toContainText(inline.text.slice(0, 40));
    // The stripped pseudo-lesson must not appear anywhere as a reading.
    await expect(page.locator('.reading-heading', { hasText: 'Coll above' })).toHaveCount(0);
  });

  test('a day offering a choice of readings announces it', async ({ page }) => {
    // The rubric is the fixed form from LITURGICAL_TEXT_REGISTER (ADR 0019
    // item 7/#77), not a per-count computed sentence — same text regardless
    // of pick/total. On a day offering a choice, both the section intro and the
    // pick rubric render this text (count is 2).
    const date = findDay('a day offering a choice of readings', d => d.morning?.lessons_pick);
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('.seg-rubric', { hasText: 'One or two readings are read.' }).first())
      .toBeVisible({ timeout: 5000 });
    await expect(page.locator('.seg-rubric', { hasText: 'One or two readings are read.' }))
      .toHaveCount(2);
  });

  test('a day offering no choice announces none', async ({ page }) => {
    // On a day with no choice, only the section reading intro rubric renders (count is 1),
    // and no dynamic pick rubric is appended.
    const date = findDay('a day offering no choice of readings',
      d => d.morning && !d.morning.lessons_pick && (d.morning.lessons || []).length);
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('.office-section-title').first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.seg-rubric', { hasText: 'One or two readings are read.' }))
      .toHaveCount(1);
  });

  test('the litany divine title reaches the page with its capital (#4)', async ({ page }) => {
    // The response belongs to ordinary-wednesday-mp, and form selection reads
    // the season before the weekday — a Wednesday in Christmastide renders
    // christmas-mp — so both have to be asked for.
    const date = findDay('a Wednesday in Ordinary Time', d =>
      new Date(d.date + 'T12:00:00Z').getUTCDay() === 3 && d.rank === 'feria'
      && d.morning && seasonFor(d.date) === 'OrdinaryTime');
    await gotoOffice(page, date, 'mp');
    const body = page.locator('body');
    await expect(body).toContainText('Holy One, accomplish your purposes in us.', { timeout: 5000 });
    await expect(body).not.toContainText('holy one, accomplish');
  });
});
