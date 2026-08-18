// @ts-check
import { expect } from '@playwright/test';

// Hash-based routing (#/DATE/OFFICE) was removed 2026-07-19 (see web/app.js
// "Navigation" comment) — navigateTo() and initPage() never touch the URL.
// A fresh page.goto('/') always lands on today + the time-of-day default
// office, and any leftover #/DATE/OFFICE hash gets stripped on load. Reach a
// specific date/office by driving the real UI instead: the date picker for
// the date, then the office toggle for MP/EP.

/**
 * #day-date-picker lives inside the date/office picker sheet (#day-picker-sheet,
 * aria-hidden by default) — open it via the nav bar's calendar button before
 * interacting with the input.
 */
export async function openDatePicker(page) {
  await page.locator('#nav-cal-btn').click();
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
 * Drive the Office segmented control in the day header until the requested
 * office shows. One path at every width now: the control is always visible, so
 * there is no breakpoint-dependent fallback through the picker sheet.
 */
export async function ensureOffice(page, office) {
  const label = office === 'ep' ? 'Evening Prayer'
    : office === 'midday' ? 'Mid-day Prayer' : 'Morning Prayer';
  const btn = page.locator(`.day-ctrl-group--office .day-ctrl-btn:text-is("${label}")`);
  if ((await btn.getAttribute('aria-pressed')) !== 'true') {
    await btn.click();
  }
  await expect(btn).toHaveAttribute('aria-pressed', 'true');
}
