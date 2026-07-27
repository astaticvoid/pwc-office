// @ts-check
import { expect } from '@playwright/test';

// Hash-based routing (#/DATE/OFFICE) was removed 2026-07-19 (see web/app.js
// "Navigation" comment) — navigateTo() and initPage() never touch the URL.
// A fresh page.goto('/') always lands on today + the time-of-day default
// office, and any leftover #/DATE/OFFICE hash gets stripped on load. Reach a
// specific date/office by driving the real UI instead: the date picker for
// the date, then the office toggle for MP/EP.

/** Navigate to a fresh load, then drive the UI to the given date/office. */
export async function gotoOffice(page, date, office) {
  await page.goto('/');
  await page.locator('#day-title').waitFor();
  await page.locator('#day-date-picker').fill(date);
  await ensureOffice(page, office);
}

/** Click the #day-office-name toggle until it shows the requested office. */
export async function ensureOffice(page, office) {
  const label = office === 'ep' ? 'Evening Prayer' : 'Morning Prayer';
  const el = page.locator('#day-office-name');
  if ((await el.textContent()) !== label) {
    await el.click();
  }
  await expect(el).toHaveText(label);
}
