// @ts-check
import { expect } from '@playwright/test';

// Hash-based routing (#/DATE/OFFICE) was removed 2026-07-19 (see web/app.js
// "Navigation" comment) — navigateTo() and initPage() never touch the URL.
// A fresh page.goto('/') always lands on today + the time-of-day default
// office, and any leftover #/DATE/OFFICE hash gets stripped on load. Reach a
// specific date/office by driving the real UI instead: the date picker for
// the date, then the office toggle for MP/EP.

/**
 * #day-date-picker lives inside the day-picker bottom sheet (#day-picker-sheet,
 * aria-hidden by default) — open it via the date button or the day title
 * before interacting with the input.
 */
export async function openDatePicker(page) {
  await page.locator('#day-date-btn').click();
  await expect(page.locator('#day-date-picker')).toBeVisible();
}

/** Navigate to a fresh load, then drive the UI to the given date/office. */
export async function gotoOffice(page, date, office) {
  await page.goto('/');
  await page.locator('#day-title').waitFor();
  await openDatePicker(page);
  await page.locator('#day-date-picker').fill(date);
  await ensureOffice(page, office);
}

/**
 * Matches the desktop breakpoint in web/office.css (@media (min-width: 820px)).
 * On narrower ("mobile") viewports, tapping #day-office-name opens the day
 * picker sheet instead of flipping office directly (web/app.js isMobileLayout).
 */
async function isMobileLayout(page) {
  return page.evaluate(() => window.matchMedia('(max-width: 819.98px)').matches);
}

/** Drive #day-office-name (or the mobile picker sheet it opens) until the requested office shows. */
export async function ensureOffice(page, office) {
  const label = office === 'ep' ? 'Evening Prayer' : 'Morning Prayer';
  const el = page.locator('#day-office-name');
  if ((await el.textContent()) !== label) {
    if (await isMobileLayout(page)) {
      await el.click();
      await page.locator(office === 'ep' ? '#day-picker-ep' : '#day-picker-mp').click();
      await page.locator('#settings-close-btn').click();
    } else {
      await el.click();
    }
  }
  await expect(el).toHaveText(label);
}
