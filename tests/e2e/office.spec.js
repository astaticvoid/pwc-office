// @ts-check
import { test, expect } from '@playwright/test';

// Use a fixed known-good date rather than today so tests don't break
// on days with unusual structure (e.g. no alternate, no optional lesson).
// 2026-05-17 (Seventh Sunday of Easter) has:
//   - MP + EP
//   - Two alternate observances (Easter VII + Ascension)
//   - Two lessons per office
//   - Long pastoral note (tests note expand/collapse)
const DATE  = '2026-05-17';
const MP    = `/#/${DATE}/mp`;
const EP    = `/#/${DATE}/ep`;
const PREV  = `/#/2026-05-16/mp`;

// How long to wait for async content (psalms, scripture fetches).
const CONTENT_TIMEOUT = 20_000;

// ── Helpers ───────────────────────────────────────────────────────────────────

async function waitForContentLoaded(page) {
  // All .psalm-loading and .scripture-placeholder divs must have resolved.
  await expect(page.locator('.psalm-loading p.loading')).toHaveCount(0, { timeout: CONTENT_TIMEOUT });
  await expect(page.locator('.scripture-placeholder p.loading')).toHaveCount(0, { timeout: CONTENT_TIMEOUT });
}

// ── Office loads ──────────────────────────────────────────────────────────────

test.describe('Office loads', () => {
  test('morning prayer: page title and header', async ({ page }) => {
    await page.goto(MP);
    await expect(page).toHaveTitle(/Morning Prayer/);
    await expect(page.locator('#day-title')).toContainText('Easter');
    await expect(page.locator('#day-subtitle')).toContainText('2026');
    await expect(page.locator('#day-office-name')).toHaveText('Morning Prayer');
  });

  test('morning prayer: psalms render with number and verses', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator('.psalm-title').first()).toBeVisible({ timeout: CONTENT_TIMEOUT });
    // Psalm title should include "Psalm N"
    await expect(page.locator('.psalm-title').first()).toContainText('Psalm');
    // At least one verse should be rendered (verse numbers hidden in non-book mode)
    await expect(page.locator('.psalm-block').first()).not.toBeEmpty();
  });

  test('morning prayer: no loading spinners remain', async ({ page }) => {
    await page.goto(MP);
    await waitForContentLoaded(page);
    // Nothing should still be loading
    await expect(page.locator('p.loading')).toHaveCount(0);
  });

  test('morning prayer: scripture fills in without errors', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await expect(page.locator('.error-msg')).toHaveCount(0);
  });

  test('morning prayer: all major sections present', async ({ page }) => {
    await page.goto(MP);
    const sections = page.locator('.office-section-title');
    // Gathering, Proclamation, Prayers, Sending
    await expect(sections).toHaveCount(4);
  });

  test('morning prayer: collect appears in Prayers section', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator('.office-section-title', { hasText: 'Prayers' })).toBeVisible();
    await expect(page.locator('.office-subsection-title', { hasText: 'Collect' }).first())
      .toBeVisible({ timeout: 5000 });
  });

  test('morning prayer: reading headings use full book names', async ({ page }) => {
    await page.goto(MP);
    // Reading headings should say e.g. "Numbers" not "Num", "Ephesians" not "Eph"
    const headings = page.locator('.reading-heading');
    await expect(headings.first()).toBeVisible({ timeout: CONTENT_TIMEOUT });
    const text = await headings.first().textContent();
    // Should not contain bare two/three-letter abbreviations like "Num" or "Eph"
    expect(text).not.toMatch(/Reading:\s+[A-Z][a-z]{0,2}\s+\d/);
  });

  test('morning prayer: psalm ends with gloria toggle', async ({ page }) => {
    await page.goto(MP);
    const firstGloria = page.locator('.psalm-gloria').first();
    await expect(firstGloria).toBeVisible({ timeout: CONTENT_TIMEOUT });
    // Each psalm gloria has exactly 3 tabs; scope to the first one.
    await expect(firstGloria.locator('.alt-tab')).toHaveCount(3);
  });

  test('morning prayer: reading ends with 3-option thanks-be-to-god', async ({ page }) => {
    await page.goto(MP);
    // Scope to primary readings only — alternate readings also render response tabs.
    const responseTabs = page.locator('.obs-readings[data-obs="primary"] [data-key="pwc-alt-reading_response"]');
    await expect(responseTabs.first()).toBeVisible({ timeout: CONTENT_TIMEOUT });
    await expect(responseTabs).toHaveCount(6); // 3 tabs × 2 lessons = 6
  });

  test('morning prayer: affirmation is in Proclamation, not Prayers', async ({ page }) => {
    await page.goto(MP);
    const affirmation = page.locator('.office-subsection-title', { hasText: 'Affirmation' });
    await expect(affirmation).toBeVisible({ timeout: 5000 });
    // Affirmation title must appear BEFORE the Prayers section title
    const proclamation = page.locator('.office-section-title', { hasText: 'Proclamation' });
    const prayers      = page.locator('.office-section-title', { hasText: 'Prayers' });
    const affirmBB = await affirmation.boundingBox();
    const prayersBB = await prayers.boundingBox();
    expect(affirmBB.y).toBeLessThan(prayersBB.y);
  });

  test('evening prayer loads', async ({ page }) => {
    await page.goto(EP);
    await expect(page).toHaveTitle(/Evening Prayer/);
    await expect(page.locator('.psalm-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await expect(page.locator('.error-msg')).toHaveCount(0);
  });

  test('evening prayer: introductory responses has 2 tabs (not 5)', async ({ page }) => {
    await page.goto(EP);
    const altBlock = page.locator('.alt-block').first();
    await altBlock.waitFor();
    await expect(altBlock.locator(':scope > .alt-tabs > .alt-tab')).toHaveCount(2);
  });

  test('evening prayer: Thanksgiving section present', async ({ page }) => {
    await page.goto(EP);
    await expect(page.locator('.office-subsection-title', { hasText: 'Thanksgiving' }))
      .toBeVisible({ timeout: 5000 });
  });
});

// ── Navigation ────────────────────────────────────────────────────────────────

// The nav was redesigned: the ← → arrows are hidden (kept in the DOM for
// keyboard shortcuts only — see the Keyboard navigation describe), day-jump is
// the calendar date-picker, "today" is the brand logo, and the MP/EP toggle
// lives in the day-header controls (.day-ctrl-btn).
test.describe('Navigation', () => {
  test('date picker navigates to a chosen date', async ({ page }) => {
    await page.goto(MP);
    await page.locator('#nav-date-picker').fill('2026-05-16');
    await expect(page).toHaveURL(/2026-05-16\/mp/);
    await expect(page.locator('#day-title')).not.toBeEmpty();
  });

  test('MP/EP toggle switches office', async ({ page }) => {
    await page.goto(MP);
    await page.locator('.day-ctrl-btn', { hasText: 'Evening Prayer' }).click();
    await expect(page).toHaveURL(/2026-05-17\/ep/);
    await expect(page).toHaveTitle(/Evening Prayer/);
  });

  test('brand logo navigates to today', async ({ page }) => {
    // Start on a different date
    await page.goto(PREV);
    await page.locator('#nav-brand').click();
    // Brand clears the hash to bare "/" and renders today; the date picker
    // reflects the rendered date (picker.value = dateStr in render()).
    const today = new Date();
    const pad = n => String(n).padStart(2, '0');
    const todayStr = `${today.getFullYear()}-${pad(today.getMonth()+1)}-${pad(today.getDate())}`;
    await expect(page.locator('#nav-date-picker')).toHaveValue(todayStr);
  });
});

// ── Keyboard navigation (desktop only) ───────────────────────────────────────

test.describe('Keyboard navigation', () => {
  test('keyboard right/left arrow navigates', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'mobile', 'Keyboard shortcuts are desktop-only');
    await page.goto(MP);
    await expect(page.locator('#day-title')).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await page.keyboard.press('ArrowRight');
    await expect(page).toHaveURL(/2026-05-18\/mp/);
    await page.keyboard.press('ArrowLeft');
    await expect(page).toHaveURL(/2026-05-17\/mp/);
  });

  test('keyboard m/e switches office', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'mobile', 'Keyboard shortcuts are desktop-only');
    await page.goto(MP);
    await expect(page.locator('#day-title')).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await page.keyboard.press('e');
    await expect(page).toHaveURL(/ep$/);
    await page.keyboard.press('m');
    await expect(page).toHaveURL(/mp$/);
  });
});

// ── Notes ─────────────────────────────────────────────────────────────────────

test.describe('Notes', () => {
  test('long note is truncated by default', async ({ page }) => {
    await page.goto(MP);
    const expandBtn = page.locator('.note-expand-btn').first();
    await expect(expandBtn).toBeVisible({ timeout: 5000 });
    await expect(expandBtn).toHaveText('Read more');
    // The containing note paragraph should show truncated text with ellipsis
    const noteText = await page.locator('p.day-note').first().textContent();
    expect(noteText).toMatch(/…/);
  });

  test('clicking Read More expands note to full text', async ({ page }) => {
    await page.goto(MP);
    const expandBtn = page.locator('.note-expand-btn').first();
    await expect(expandBtn).toBeVisible({ timeout: 5000 });
    const shortText = await page.locator('p.day-note').first().textContent();
    expect(shortText).toMatch(/…/);

    await expandBtn.click();

    // Button is gone, full text is shown
    const fullText = await page.locator('p.day-note').first().textContent();
    expect(fullText).not.toMatch(/…/);
    expect((fullText || '').length).toBeGreaterThan((shortText || '').length);
  });
});

// ── Alternatives toggles ──────────────────────────────────────────────────────

test.describe('Alternatives', () => {
  test('opening responses has 2 tabs (Form I and II)', async ({ page }) => {
    await page.goto(MP);
    // The first alt-block in the Gathering section should be the opening responses.
    const altBlock = page.locator('.alt-block').first();
    await altBlock.waitFor();
    // Use :scope to avoid counting nested Berakah tabs (which are inside Form II's panel).
    await expect(altBlock.locator(':scope > .alt-tabs > .alt-tab')).toHaveCount(2);
    await expect(altBlock.locator(':scope > .alt-tabs > .alt-tab').nth(0)).toHaveClass(/alt-tab-active/);
  });

  test('Form II contains nested Berakah blessings toggle', async ({ page }) => {
    await page.goto(MP);
    const outer = page.locator('.alt-block').first();
    await outer.waitFor();

    // Click Form II
    await outer.locator('.alt-tab').nth(1).click();
    await expect(outer.locator('.alt-tab').nth(1)).toHaveClass(/alt-tab-active/);

    // There should now be a nested alt-block (the Berakah blessings) visible
    const panel = outer.locator('.alt-panel').nth(1);
    const nested = panel.locator('.alt-block');
    await expect(nested).toBeVisible();
    await expect(nested.locator('.alt-tab')).toHaveCount(3);
    // Blessing I should be selected by default
    await expect(nested.locator('.alt-tab').nth(0)).toHaveClass(/alt-tab-active/);
  });

  test('clicking tab shows correct panel, hides others', async ({ page }) => {
    await page.goto(MP);
    const altBlock = page.locator('.alt-block').first();
    await altBlock.waitFor();

    // Tab II
    await altBlock.locator('.alt-tab').nth(1).click();
    await expect(altBlock.locator('.alt-panel').nth(0)).toHaveClass(/alt-panel-hidden/);
    await expect(altBlock.locator('.alt-panel').nth(1)).not.toHaveClass(/alt-panel-hidden/);

    // Back to tab I
    await altBlock.locator('.alt-tab').nth(0).click();
    await expect(altBlock.locator('.alt-panel').nth(0)).not.toHaveClass(/alt-panel-hidden/);
    await expect(altBlock.locator('.alt-panel').nth(1)).toHaveClass(/alt-panel-hidden/);
  });

  test('tab selection persists across office switch', async ({ page }) => {
    await page.goto(MP);
    const altBlock = page.locator('.alt-block').first();
    await altBlock.waitFor();

    // Select tab II
    await altBlock.locator('.alt-tab').nth(1).click();

    // Switch to EP and back to MP (day-header office toggle)
    await page.locator('.day-ctrl-btn', { hasText: 'Evening Prayer' }).click();
    await page.locator('.day-ctrl-btn', { hasText: 'Morning Prayer' }).click();

    const altBlockAfter = page.locator('.alt-block').first();
    await altBlockAfter.waitFor();
    await expect(altBlockAfter.locator('.alt-tab').nth(1)).toHaveClass(/alt-tab-active/);
  });

  test('nested Berakah blessings survive round-trip tab switch (II → I → II)', async ({ page }) => {
    await page.goto(MP);
    const outer = page.locator('.alt-block').first();
    await outer.waitFor();

    // Switch to Form II to reveal the nested Berakah blessings block.
    await outer.locator('.alt-tab').nth(1).click();
    const panel2 = outer.locator('.alt-panel').nth(1);
    const berakah = panel2.locator('.alt-block');
    await expect(berakah).toBeVisible();

    // Note which blessing is active.
    const activeTabBefore = berakah.locator('.alt-tab-active');
    const labelBefore = await activeTabBefore.textContent();

    // Switch to Form I and back to Form II.
    await outer.locator('.alt-tab').nth(0).click();
    await outer.locator('.alt-tab').nth(1).click();

    // Berakah block must still be visible and have the same active tab.
    await expect(berakah).toBeVisible();
    await expect(berakah.locator('.alt-tab-active')).toHaveText(String(labelBefore));
    // Exactly one panel must be visible inside the Berakah block.
    await expect(berakah.locator('.alt-panel:not(.alt-panel-hidden)')).toHaveCount(1);
  });

  test('doxology and Berakah blessings use independent localStorage keys', async ({ page }) => {
    await page.goto(MP);
    const altBlocks = page.locator('.alt-block');
    await altBlocks.first().waitFor();

    // Open Form II to expose the Berakah blessings nested block
    await altBlocks.first().locator('.alt-tab').nth(1).click();
    const berakahBlock = altBlocks.first().locator('.alt-panel').nth(1).locator('.alt-block');
    // Select Berakah blessing III
    await berakahBlock.locator('.alt-tab').nth(2).click();

    // Find the doxology block (after the canticle section, 3 tabs starting with Roman numerals)
    // It should be independent — tab I still active
    const doxologyBlock = page.locator('.alt-block').filter({
      has: page.locator('.alt-tab', { hasText: 'I' }),
    }).last();
    await expect(doxologyBlock.locator('.alt-tab').nth(0)).toHaveClass(/alt-tab-active/);
  });
});

// ── Service worker / offline ──────────────────────────────────────────────────

test.describe('Service worker', () => {
  test('app loads offline after initial online visit', async ({ page, context }, testInfo) => {
    // SW is intentionally not registered on localhost — skip when running locally.
    test.skip((process.env.BASE_URL || 'http://localhost:8080').startsWith('http://localhost'), 'SW not registered on localhost');
    // First visit online — warms the SW cache (shell + all fetched data).
    await page.goto(MP);
    await waitForContentLoaded(page);

    // Wait for SW to take control of the page.
    await page.waitForFunction(
      () => navigator.serviceWorker.controller !== null,
      { timeout: 5000 }
    );

    // Go offline and reload — everything should come from the SW cache.
    await context.setOffline(true);
    try {
      await page.reload();
      await expect(page).toHaveTitle(/Morning Prayer/);
      await expect(page.locator('#day-title')).not.toBeEmpty();
      await expect(page.locator('.office-section-title').first()).toBeVisible({ timeout: 5000 });
    } finally {
      await context.setOffline(false);
    }
  });
});

// ── Date picker ───────────────────────────────────────────────────────────────

test.describe('Date picker', () => {
  test('changing date navigates to that day', async ({ page }) => {
    await page.goto(MP);
    await page.locator('#day-title').waitFor();
    await page.locator('#nav-date-picker').fill('2026-05-18');
    await page.locator('#nav-date-picker').dispatchEvent('change');
    await expect(page).toHaveURL(/2026-05-18\/mp/);
    await expect(page.locator('#day-title')).not.toBeEmpty();
  });
});

// ── Translation switch ────────────────────────────────────────────────────────

test.describe('Translation switch', () => {
  test('switching to KJV re-renders scripture', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    const before = await page.locator('.scripture-placeholder').first().textContent();

    await page.locator('#nav-translation').selectOption('kjv');
    // Wait for loading state to clear
    await expect(page.locator('.scripture-placeholder p.loading')).toHaveCount(0, { timeout: CONTENT_TIMEOUT });
    const after = await page.locator('.scripture-placeholder').first().textContent();
    // KJV and NRSVUE differ in wording
    expect(after).not.toBe(before);
  });

  test('translation preference persists across navigation', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await page.locator('#nav-translation').selectOption('kjv');

    // Navigate to the next day (arrows are keyboard-only now; go by URL).
    await page.goto('/#/2026-05-18/mp');
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await expect(page.locator('#nav-translation')).toHaveValue('kjv');
    await expect(page.locator('#scripture-attr')).toContainText('KJV');
  });
});

// ── Observance toggle ─────────────────────────────────────────────────────────

// The observance switch moved into the day-header controls
// (.day-ctrl-group--obs): a primary/alternate segmented control whose buttons
// are hash links (…/mp/primary, …/mp/alternate).
const OBS_ALT = 'a.day-ctrl-btn[href*="/alternate"]';

test.describe('Observance toggle', () => {
  // 2026-05-17 has Easter VII (primary) and Ascension (alternate)
  test('observance control is visible', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator('.day-ctrl-group--obs')).toBeVisible({ timeout: 5000 });
    await expect(page.locator(OBS_ALT)).toBeVisible();
  });

  test('primary readings visible by default, alternate hidden', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator('.obs-readings[data-obs="primary"]')).not.toHaveClass(/obs-hidden/);
    await expect(page.locator('.obs-readings[data-obs="alternate"]')).toHaveClass(/obs-hidden/);
  });

  test('clicking alternate observance swaps visible readings', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page.locator('.obs-readings[data-obs="primary"]')).toHaveClass(/obs-hidden/);
    await expect(page.locator('.obs-readings[data-obs="alternate"]')).not.toHaveClass(/obs-hidden/);
  });

  test('title updates to reflect alternate observance', async ({ page }) => {
    await page.goto(MP);
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page).toHaveTitle(/Ascension/, { timeout: 5000 });
  });

  test('collect updates to alternate observance collect', async ({ page }) => {
    await page.goto(MP);
    // Primary: Seventh Sunday of Easter (collect 344)
    await expect(page.locator('#prayers-collect')).toContainText('Seventh Sunday of Easter', { timeout: 5000 });
    // Switch to Ascension (collect 343)
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page.locator('#prayers-collect')).toContainText('Ascension of the Lord', { timeout: 5000 });
    // Switch back — the primary observance button is the first in the obs
    // segment (its href has no "/primary" suffix; primary is the default).
    await page.locator('.day-ctrl-seg--obs .day-ctrl-btn').first().click();
    await expect(page.locator('#prayers-collect')).toContainText('Seventh Sunday of Easter', { timeout: 5000 });
  });
});

// ── BUG-19 regression ─────────────────────────────────────────────────────────

test.describe('Reading response renders after lesson', () => {
  for (const [label, date, office] of [
    ['seasonal (Lent)', '2026-02-25', 'mp'],
    ['ordinary-time', '2026-06-17', 'mp'],
  ]) {
    test(label, async ({ page }) => {
      await page.goto(`/#/${date}/${office}`);
      // Wait for scripture to load (replaces placeholder)
      await page.waitForSelector('.scripture-placeholder:not(:has(.loading))', { timeout: 10000 });
      // The reading-response tab strip is the .alt-block containing the
      // "The word of the Lord" versicle. Scope to it — the page has many other
      // alt-blocks (collect, canticle, affirmation), so a page-wide count is wrong.
      const rrBlock = page.locator('.alt-block', { hasText: 'The word of the Lord' }).first();
      await expect(rrBlock.locator('.alt-tabs')).toBeVisible();
      // Must have 3 options (I / II / III)
      await expect(rrBlock.locator(':scope > .alt-tabs > .alt-tab')).toHaveCount(3);
    });
  }
});

test("Lord's Prayer present in ordinary-time office", async ({ page }) => {
  await page.goto('/#/2026-06-17/mp');
  await expect(page.locator('.office-subsection-title', { hasText: "The Lord's Prayer" })).toBeVisible();
});

// ── Season theming (JS/Go parity) ────────────────────────────────────────────
// These boundary dates must agree with TestFormSeasonOf in season_test.go.
// A failure here means seasonOf() or officeFormSeason() in app.js has drifted
// from the Go implementations in season.go.

test.describe('Season theming parity', () => {
  const cases = [
    // data-season is set by seasonOf() in app.js
    { date: '2025-11-30', season: 'Advent',       label: 'Advent I' },
    { date: '2025-12-25', season: 'Christmas',    label: 'Christmas Day' },
    { date: '2026-01-11', season: 'Epiphany',     label: 'Baptism of the Lord' },
    { date: '2026-02-18', season: 'Lent',         label: 'Ash Wednesday' },
    { date: '2026-03-22', season: 'Passiontide',  label: '5th Sunday in Lent' },
    { date: '2026-04-05', season: 'Easter',       label: 'Easter Day' },
    // Ascension: seasonOf uses Pentecost as season boundary (not Ascension)
    { date: '2026-05-14', season: 'Easter',       label: 'Ascension — still Easter theme' },
    { date: '2026-05-24', season: 'Pentecost',    label: 'Pentecost Sunday' },
    { date: '2026-11-01', season: 'AllSaints',    label: 'All Saints' },
    { date: '2026-11-29', season: 'Advent',       label: 'Advent I (year N+1)' },
    { date: '2026-12-25', season: 'Christmas',    label: 'Christmas Day 2026' },
  ];

  for (const { date, season, label } of cases) {
    test(`${label}: data-season="${season}"`, async ({ page }) => {
      await page.goto(`/#/${date}/mp`);
      await page.locator('#day-title').waitFor({ timeout: 5000 });
      await expect(page.locator('html')).toHaveAttribute('data-season', season);
    });
  }
});
