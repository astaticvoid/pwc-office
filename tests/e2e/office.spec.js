// @ts-check
import { test, expect } from '@playwright/test';
import { gotoOffice, ensureOffice, openDatePicker } from './helpers.js';

// Use a fixed known-good date rather than today so tests don't break
// on days with unusual structure (e.g. no alternate, no optional lesson).
// 2026-05-17 (Seventh Sunday of Easter) has:
//   - MP + EP
//   - Two alternate observances (Easter VII + Ascension)
//   - Two lessons per office
//   - Long pastoral note (tests note expand/collapse)
const DATE      = '2026-05-17';
const DATE_PREV = '2026-05-16';
const DATE_NEXT = '2026-05-18';

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
  test('morning prayer: page title and header @smoke', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page).toHaveTitle(/Morning Prayer/);
    await expect(page.locator('#day-title')).toContainText('Easter');
    await expect(page.locator('#day-date-label')).toContainText('2026');
    await expect(page.locator('#day-office-name')).toHaveText('Morning Prayer');
  });

  test('morning prayer: psalms render with number and verses @smoke', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator('.psalm-title').first()).toBeVisible({ timeout: CONTENT_TIMEOUT });
    // Psalm title should include "Psalm N"
    await expect(page.locator('.psalm-title').first()).toContainText('Psalm');
    // At least one verse should be rendered, with its verse number visible
    await expect(page.locator('.psalm-block').first()).not.toBeEmpty();
    await expect(page.locator('.psalm-block sup').first()).toBeVisible();
  });

  test('morning prayer: no loading spinners remain @smoke', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await waitForContentLoaded(page);
    // Nothing should still be loading
    await expect(page.locator('p.loading')).toHaveCount(0);
  });

  test('morning prayer: scripture fills in without errors @smoke', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await expect(page.locator('.error-msg')).toHaveCount(0);
  });

  test('morning prayer: all major sections present @smoke', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const sections = page.locator('.office-section-title');
    // Gathering, Proclamation, Prayers, Sending
    await expect(sections).toHaveCount(4);
  });

  test('morning prayer: collect appears in Prayers section', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator('.office-section-title', { hasText: 'Prayers' })).toBeVisible();
    await expect(page.locator('.office-subsection-title', { hasText: 'Collect' }).first())
      .toBeVisible({ timeout: 5000 });
  });

  test('morning prayer: reading headings use full book names', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    // Reading headings should say e.g. "Numbers" not "Num", "Ephesians" not "Eph"
    const headings = page.locator('.reading-heading');
    await expect(headings.first()).toBeVisible({ timeout: CONTENT_TIMEOUT });
    const text = await headings.first().textContent();
    // Should not contain bare two/three-letter abbreviations like "Num" or "Eph"
    expect(text).not.toMatch(/Reading:\s+[A-Z][a-z]{0,2}\s+\d/);
  });

  test('morning prayer: psalm ends with gloria toggle', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const firstGloria = page.locator('.psalm-gloria').first();
    await expect(firstGloria).toBeVisible({ timeout: CONTENT_TIMEOUT });
    // Each psalm gloria has exactly 3 tabs; scope to the first one.
    await expect(firstGloria.locator('.alt-tab')).toHaveCount(3);
  });

  test('morning prayer: reading ends with 3-option thanks-be-to-god', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    // Scope to primary readings only — alternate readings also render response tabs.
    const responseTabs = page.locator('.obs-readings[data-obs="primary"] [data-key="pwc-alt-reading_response"]');
    await expect(responseTabs.first()).toBeVisible({ timeout: CONTENT_TIMEOUT });
    // The reading selector (ADR 0014/#63) shows each lesson twice — once in
    // the "All" panel, once in its own individual tab — so each of the 2
    // lessons' 3 response tabs renders twice: 3 × 2 × 2 = 12.
    await expect(responseTabs).toHaveCount(12);
  });

  test('morning prayer: affirmation is in Proclamation, not Prayers', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const affirmation = page.locator('.office-subsection-title', { hasText: 'Affirmation' });
    await expect(affirmation).toBeVisible({ timeout: 5000 });
    // Affirmation title must appear BEFORE the Prayers section title
    const prayers      = page.locator('.office-section-title', { hasText: 'Prayers' });
    const affirmBB = await affirmation.boundingBox();
    const prayersBB = await prayers.boundingBox();
    expect(affirmBB.y).toBeLessThan(prayersBB.y);
  });

  test('evening prayer loads', async ({ page }) => {
    await gotoOffice(page, DATE, 'ep');
    await expect(page).toHaveTitle(/Evening Prayer/);
    await expect(page.locator('.psalm-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await expect(page.locator('.error-msg')).toHaveCount(0);
  });

  test('evening prayer: introductory responses has 2 tabs (not 5)', async ({ page }) => {
    await gotoOffice(page, DATE, 'ep');
    const altBlock = page.locator('.alt-block').first();
    await altBlock.waitFor();
    await expect(altBlock.locator(':scope > .alt-tabs > .alt-tab')).toHaveCount(2);
  });

  test('evening prayer: Thanksgiving section present', async ({ page }) => {
    await gotoOffice(page, DATE, 'ep');
    await expect(page.locator('.office-subsection-title', { hasText: 'Thanksgiving' }))
      .toBeVisible({ timeout: 5000 });
  });
});

// ── Navigation ────────────────────────────────────────────────────────────────

// The nav was redesigned: hash-based routing (#/DATE/OFFICE) was removed
// entirely (2026-07-19) — navigateTo()/initPage() in app.js never touch the
// URL, and a fresh load always lands on today + the time-of-day default
// office. Day-jump is the calendar date-picker (#day-date-picker), "today"
// is the brand logo (#nav-brand), and MP/EP is a two-button segmented control
// in the day header (.day-ctrl-group--office). #day-office-name is a label
// showing the current office, not a control.
test.describe('Navigation', () => {
  test('date picker navigates to a chosen date', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await openDatePicker(page);
    await page.locator('#day-date-picker').fill(DATE_PREV);
    await expect(page.locator('#day-date-picker')).toHaveValue(DATE_PREV);
    await expect(page.locator('#day-date-label')).toContainText('16 May 2026');
    await expect(page.locator('#day-title')).not.toBeEmpty();
  });

  // The office toggle is a visible segmented control in the day header at every
  // width, so one path serves both projects — no branch on viewport here.
  test('MP/EP toggle switches office', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const seg = page.locator('.day-ctrl-group--office');
    await expect(seg).toBeVisible();
    await expect(seg.locator('.day-ctrl-btn')).toHaveCount(2);
    await expect(seg.locator('.day-ctrl-btn.is-active')).toHaveText('Morning Prayer');

    await seg.locator('.day-ctrl-btn:text-is("Evening Prayer")').click();

    await expect(page.locator('#day-office-name')).toHaveText('Evening Prayer');
    await expect(page).toHaveTitle(/Evening Prayer/);
    await expect(seg.locator('.day-ctrl-btn.is-active')).toHaveText('Evening Prayer');
    await expect(seg.locator('.day-ctrl-btn:text-is("Evening Prayer")'))
      .toHaveAttribute('aria-pressed', 'true');
  });

  // Each control carries the other's axis in its data-navigate payload, so a
  // switch on one must not reset the other. The suite exercised the two axes
  // separately and never together, which is exactly where that would break.
  test('office and observance selections survive each other', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const obs = page.locator('.day-ctrl-group--obs');
    await expect(obs).toBeVisible();          // DATE has an alternate observance

    // pick the alternate observance, then flip office
    await obs.locator('.day-ctrl-btn').nth(1).click();
    const altLabel = await obs.locator('.day-ctrl-btn.is-active').textContent();
    await page.locator('.day-ctrl-group--office .day-ctrl-btn:text-is("Evening Prayer")').click();

    await expect(page.locator('#day-office-name')).toHaveText('Evening Prayer');
    await expect(page.locator('.day-ctrl-group--obs .day-ctrl-btn.is-active'))
      .toHaveText(String(altLabel));

    // and back the other way: flipping observance keeps the office
    await page.locator('.day-ctrl-group--obs .day-ctrl-btn').nth(0).click();
    await expect(page.locator('#day-office-name')).toHaveText('Evening Prayer');
    await expect(page.locator('.day-ctrl-group--office .day-ctrl-btn.is-active'))
      .toHaveText('Evening Prayer');
  });

  // A heading that silently swallows taps is not discoverable, so the title
  // neither opens the picker nor claims to be a button; the date does.
  test('the day title is a heading, not a control', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const title = page.locator('#day-title');
    await expect(title).not.toHaveAttribute('role', 'button');
    await expect(title).not.toHaveAttribute('tabindex', '0');
    await title.click();
    await expect(page.locator('#day-picker-sheet')).toHaveAttribute('aria-hidden', 'true');
  });

  test('brand logo navigates to today', async ({ page }) => {
    // Start on a different date
    await gotoOffice(page, DATE_PREV, 'mp');
    await page.locator('#nav-brand').click();
    // Brand resets state to today; the date picker reflects the rendered date.
    const today = new Date();
    const pad = n => String(n).padStart(2, '0');
    const todayStr = `${today.getFullYear()}-${pad(today.getMonth()+1)}-${pad(today.getDate())}`;
    await expect(page.locator('#day-date-picker')).toHaveValue(todayStr);
  });
});

// ── Notes ─────────────────────────────────────────────────────────────────────

test.describe('Notes', () => {
  test('long note is truncated by default', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const expandBtn = page.locator('.note-expand-btn').first();
    await expect(expandBtn).toBeVisible({ timeout: 5000 });
    await expect(expandBtn).toHaveText('Read more');
    // The containing note paragraph should show truncated text with ellipsis
    const noteText = await page.locator('p.day-note').first().textContent();
    expect(noteText).toMatch(/…/);
  });

  test('clicking Read More expands note to full text', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
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
    await gotoOffice(page, DATE, 'mp');
    // The first alt-block in the Gathering section should be the opening responses.
    const altBlock = page.locator('.alt-block').first();
    await altBlock.waitFor();
    // Use :scope to avoid counting nested Berakah tabs (which are inside Form II's panel).
    await expect(altBlock.locator(':scope > .alt-tabs > .alt-tab')).toHaveCount(2);
    await expect(altBlock.locator(':scope > .alt-tabs > .alt-tab').nth(0)).toHaveClass(/alt-tab-active/);
  });

  test('Form II contains nested Berakah blessings toggle', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
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
    await gotoOffice(page, DATE, 'mp');
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
    await gotoOffice(page, DATE, 'mp');
    const altBlock = page.locator('.alt-block').first();
    await altBlock.waitFor();

    // Select tab II
    await altBlock.locator('.alt-tab').nth(1).click();

    // Switch to EP and back to MP via the office segmented control
    await ensureOffice(page, 'ep');
    await ensureOffice(page, 'mp');

    const altBlockAfter = page.locator('.alt-block').first();
    await altBlockAfter.waitFor();
    await expect(altBlockAfter.locator('.alt-tab').nth(1)).toHaveClass(/alt-tab-active/);
  });

  test('nested Berakah blessings survive round-trip tab switch (II → I → II)', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
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
    await gotoOffice(page, DATE, 'mp');
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

  test('a long book-name pill wraps the row without clipping on a narrow viewport', async ({ page }) => {
    // The worst case: "A Song of Jerusalem Our Mother" (30 chars) in the
    // ordinary-saturday canticle alternatives. On a narrow viewport the pill
    // must wrap the row rather than truncate or overflow — the names are the
    // book's, and "A Song of Jerusalem Our Mo…" is worse than a second line.
    // 2026-08-22 is a feria, so it resolves to ordinary-saturday-mp.
    await page.setViewportSize({ width: 320, height: 800 });
    await gotoOffice(page, '2026-08-22', 'mp');

    const longTab = page.locator('.alt-tab', { hasText: 'A Song of Jerusalem Our Mother' });
    // Guard the fixture: if the lectionary moves and this day stops being
    // ordinary-saturday-mp, say so rather than pass blindly.
    await expect(longTab, 'fixture no longer renders the long canticle name').toHaveCount(1);

    // The full name is shown, never truncated with an ellipsis.
    await expect(longTab).toHaveText('A Song of Jerusalem Our Mother');

    // The pill stays inside the viewport — it wraps the row, doesn't overflow it.
    const box = await longTab.boundingBox();
    expect(box.x + box.width).toBeLessThanOrEqual(320);

    // And nothing on the page overflows horizontally either.
    const overflowX = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflowX).toBeLessThanOrEqual(0);
  });
});

// ── Psalm and reading selectors (ADR 0014, #63) ─────────────────────────────
// Restores an All + one-tab-per-branch selector over appointed psalms and
// readings so every branch the rite offers is reachable, not silently
// resolved to "show everything".

test.describe('Psalm and reading selectors', () => {
  test('psalm_sets renders an All + one-tab-per-set selector', async ({ page }) => {
    // 2026-04-05 evening psalm_sets: [[113, 114], [118]]
    await gotoOffice(page, '2026-04-05', 'ep');
    const psalmBlock = page.locator('.alt-block:has(> .alt-tabs > .alt-tab[data-key^="pwc-psalmset-"])').first();
    await psalmBlock.waitFor();
    const tabs = psalmBlock.locator(':scope > .alt-tabs > .alt-tab');
    await expect(tabs).toHaveCount(3); // All, "113, 114", "118"
    await expect(tabs.nth(0)).toHaveText('All');
    await expect(tabs.nth(0)).toHaveClass(/alt-tab-active/);

    // Selecting the second set isolates it: its panel shows, the others hide.
    await tabs.nth(2).click();
    await expect(psalmBlock.locator(':scope > .alt-panel').nth(0)).toHaveClass(/alt-panel-hidden/);
    await expect(psalmBlock.locator(':scope > .alt-panel').nth(2)).not.toHaveClass(/alt-panel-hidden/);
    await expect(psalmBlock.locator(':scope > .alt-panel').nth(2).locator('[data-citation="118"]')).toHaveCount(1);
  });

  test('multiple plain psalms renders an All + one-tab-per-psalm selector', async ({ page }) => {
    // 2026-01-03 evening psalms: ['29', '98']
    await gotoOffice(page, '2026-01-03', 'ep');
    const psalmBlock = page.locator('.alt-block:has(> .alt-tabs > .alt-tab[data-key^="pwc-psalm-"])').first();
    await psalmBlock.waitFor();
    const tabs = psalmBlock.locator(':scope > .alt-tabs > .alt-tab');
    await expect(tabs).toHaveCount(3); // All, Psalm 29, Psalm 98
    await expect(tabs.nth(1)).toHaveText('Psalm 29');
    await expect(tabs.nth(2)).toHaveText('Psalm 98');

    await tabs.nth(1).click();
    const panel1 = psalmBlock.locator(':scope > .alt-panel').nth(1);
    await expect(panel1).not.toHaveClass(/alt-panel-hidden/);
    // Individual panel is self-contained: just the one psalm, not the other.
    await expect(panel1.locator('[data-citation="29"]')).toHaveCount(1);
    await expect(panel1.locator('[data-citation="98"]')).toHaveCount(0);
  });

  test('multiple readings renders an All + one-tab-per-reading selector', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp'); // 2026-05-17: two lessons per office
    const readingBlock = page.locator('.alt-block:has(> .alt-tabs > .alt-tab[data-key^="pwc-reading-"])').first();
    await readingBlock.waitFor();
    const tabs = readingBlock.locator(':scope > .alt-tabs > .alt-tab');
    await expect(tabs).toHaveCount(3); // All, Reading 1, Reading 2
    await expect(tabs.nth(0)).toHaveText('All');

    // The "All" panel keeps today's full interleaved sequence.
    const panel0 = readingBlock.locator(':scope > .alt-panel').nth(0);
    await expect(panel0.locator('.reading-heading')).toHaveCount(2);

    // An individual tab isolates just that one reading — no Responsory/Canticle,
    // which are fixed-position elements tied to the full sequence, not to a
    // single reading (ADR 0014).
    await tabs.nth(1).click();
    const panel1 = readingBlock.locator(':scope > .alt-panel').nth(1);
    await expect(panel1).not.toHaveClass(/alt-panel-hidden/);
    await expect(panel1.locator('.reading-heading')).toHaveCount(1);
    await expect(panel1.locator('.office-subsection-title', { hasText: 'Responsory' })).toHaveCount(0);
    await expect(panel1.locator('.office-subsection-title', { hasText: 'Canticle' })).toHaveCount(0);
  });
});

// ── Date picker ───────────────────────────────────────────────────────────────

test.describe('Date picker', () => {
  test('changing date navigates to that day', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await page.locator('#day-title').waitFor();
    await openDatePicker(page);
    await page.locator('#day-date-picker').fill(DATE_NEXT);
    await page.locator('#day-date-picker').dispatchEvent('change');
    await expect(page.locator('#day-date-picker')).toHaveValue(DATE_NEXT);
    await expect(page.locator('#day-title')).not.toBeEmpty();
  });
});

// ── Translation switch ────────────────────────────────────────────────────────

// #nav-translation lives inside the settings sheet (#settings-sheet, aria-hidden
// by default) — open it via the nav settings button before interacting.
async function openSettings(page) {
  await page.locator('#nav-settings-btn').click();
  await expect(page.locator('#nav-translation')).toBeVisible();
}

test.describe('Translation switch', () => {
  test('switching to KJV re-renders scripture', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    const before = await page.locator('.scripture-placeholder').first().textContent();

    await openSettings(page);
    await page.locator('#nav-translation').selectOption('kjv');
    // Wait for loading state to clear
    await expect(page.locator('.scripture-placeholder p.loading')).toHaveCount(0, { timeout: CONTENT_TIMEOUT });
    const after = await page.locator('.scripture-placeholder').first().textContent();
    // KJV and NRSVUE differ in wording
    expect(after).not.toBe(before);
  });

  test('translation preference persists across navigation', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await openSettings(page);
    await page.locator('#nav-translation').selectOption('kjv');
    await page.locator('#settings-close-btn').click();

    // Navigate to the next day via the date picker (no hash routing anymore).
    await openDatePicker(page);
    await page.locator('#day-date-picker').fill(DATE_NEXT);
    await expect(page.locator('.scripture-block').first()).not.toBeEmpty({ timeout: CONTENT_TIMEOUT });
    await expect(page.locator('#nav-translation')).toHaveValue('kjv');
    await expect(page.locator('#scripture-attr')).toContainText('KJV');
  });
});

// ── Observance toggle ─────────────────────────────────────────────────────────

// The observance switch lives in the day-header controls
// (.day-ctrl-group--obs): a primary/alternate segmented control of
// <button data-navigate="DATE|OFFICE|primary|alternate"> elements.
const OBS_ALT = '.day-ctrl-btn[data-navigate*="|alternate"]';

test.describe('Observance toggle', () => {
  // 2026-05-17 has Easter VII (primary) and Ascension (alternate)
  test('observance control is visible', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator('.day-ctrl-group--obs')).toBeVisible({ timeout: 5000 });
    await expect(page.locator(OBS_ALT)).toBeVisible();
  });

  test('primary readings visible by default, alternate hidden', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator('.obs-readings[data-obs="primary"]')).not.toHaveClass(/obs-hidden/);
    await expect(page.locator('.obs-readings[data-obs="alternate"]')).toHaveClass(/obs-hidden/);
  });

  test('clicking alternate observance swaps visible readings', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page.locator('.obs-readings[data-obs="primary"]')).toHaveClass(/obs-hidden/);
    await expect(page.locator('.obs-readings[data-obs="alternate"]')).not.toHaveClass(/obs-hidden/);
  });

  test('title updates to reflect alternate observance', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page).toHaveTitle(/Ascension/, { timeout: 5000 });
  });

  test('collect updates to alternate observance collect', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    // Primary: Seventh Sunday of Easter (collect 344)
    await expect(page.locator('#prayers-collect')).toContainText('Seventh Sunday of Easter', { timeout: 5000 });
    // Switch to Ascension (collect 343)
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page.locator('#prayers-collect')).toContainText('Ascension of the Lord', { timeout: 5000 });
    // Switch back — the primary observance button is the first in the obs
    // segment (its data-navigate ends "|primary").
    await page.locator('.day-ctrl-seg--obs .day-ctrl-btn').first().click();
    await expect(page.locator('#prayers-collect')).toContainText('Seventh Sunday of Easter', { timeout: 5000 });
  });

  // ADR 0018: the toggle presents the selected observance's identity, not
  // just its readings — colour chips and rank chip follow the toggle.
  test('colour chip updates to the alternate observance colour', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    // Primary: Seventh Sunday of Easter (White)
    await expect(page.locator('.colour-name')).toContainText('White', { timeout: 5000 });
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    // Alternate: Ascension Sunday (White or Gold)
    await expect(page.locator('.colour-name')).toContainText('White or Gold', { timeout: 5000 });
  });

  test('rank chip follows the alternate observance', async ({ page }) => {
    // 2026-12-26: Saint Stephen, Deacon & Martyr (Holy Day) OR Feria.
    await gotoOffice(page, '2026-12-26', 'mp');
    await expect(page.locator('#day-meta')).toContainText('Holy Day', { timeout: 5000 });
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page.locator('#day-meta')).toContainText('Feria', { timeout: 5000 });
  });

  // #132: a rubric standing where a branch's name would stand is set as a
  // rubric. The observance caption is small spaced capitals, which is a
  // reasonable setting for "Feria" and not for a sentence.
  test('a rubric heading an office is set as a rubric, not as an observance name', async ({ page }) => {
    // 2026-04-04 EP — the office is conditional on the Great Vigil.
    await gotoOffice(page, '2026-04-04', 'ep');
    const rubric = page.locator('.office-rubric');
    await expect(rubric).toHaveText('This office is only to be used before the Great Vigil');
    await expect(page.locator('.observance-label')).toHaveCount(0);
    await expect(rubric).toHaveCSS('text-transform', 'none');
  });

  // ADR 0018 as amended (#133): an alternate the name column never identifies
  // shows no colour or rank rather than the primary's. The season stays — it
  // is a fact about the date, not about the observance.
  test('an alternate with no identity of its own shows no colour or rank', async ({ page }) => {
    // 2026-01-12: The Holy Innocents (Red, Holy Day) or the feria, which the
    // name column does not name and so cannot colour.
    await gotoOffice(page, '2026-01-12', 'mp');
    await expect(page.locator('#day-meta')).toContainText('Holy Day', { timeout: 5000 });
    await expect(page.locator('#day-meta .colour-name')).toHaveText('Red');

    await page.locator(OBS_ALT).click();
    await expect(page.locator('#day-meta')).not.toContainText('Holy Day');
    await expect(page.locator('#day-meta .colour-name')).toHaveCount(0);
    await expect(page.locator('#day-meta')).toContainText('Epiphany');

    // Back to the primary and both return — suppression is about the slot,
    // not a one-way erase of the header.
    await page.locator('.day-ctrl-seg--obs .day-ctrl-btn').first().click();
    await expect(page.locator('#day-meta')).toContainText('Holy Day');
    await expect(page.locator('#day-meta .colour-name')).toHaveText('Red');
  });

  // The label is the whole name, at any length: the control is the only place
  // the primary observance is named, and touch has no hover (#82).
  test('a long observance name is written out in full', async ({ page }) => {
    // 2026-06-03 MP carries the longest name in the window, at 69 characters.
    await gotoOffice(page, '2026-06-03', 'mp');
    const primary = page.locator('.day-ctrl-seg--obs .day-ctrl-btn').first();
    await expect(primary).toHaveText(
      'Martyrs of Uganda, 1886, and Janani Luwum, Archbishop of Uganda, 1977');
  });

  // Writing the name out costs nothing if the segment then leaves the column:
  // above the 820px step the control group is sized by its content, so the
  // segment's own max-width has to be clamped against something narrower.
  test('the segment stays inside the header column and keeps its 44px target', async ({ page }) => {
    await gotoOffice(page, '2026-06-06', 'ep');   // long name against a long alternate
    await expect(page.locator('.day-ctrl-group--obs')).toBeVisible({ timeout: 5000 });
    const box = await page.evaluate(() => {
      const right = sel => document.querySelector(sel).getBoundingClientRect().right;
      return {
        overflow: right('.day-ctrl-seg--obs') - right('#day-header'),
        pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        minHeight: Math.min(...[...document.querySelectorAll('.day-ctrl-seg--obs .day-ctrl-btn')]
          .map(b => b.getBoundingClientRect().height)),
      };
    });
    expect(box.overflow).toBeLessThanOrEqual(0.5);
    expect(box.pageOverflow).toBeLessThanOrEqual(0);
    expect(box.minHeight).toBeGreaterThanOrEqual(44);
  });
});

// ── Section shapes the renderer depends on ───────────────────────────────────

test.describe('Reading response renders after lesson', () => {
  for (const [label, date, office] of [
    ['seasonal (Lent)', '2026-02-25', 'mp'],
    ['ordinary-time', '2026-06-17', 'mp'],
  ]) {
    test(label, async ({ page }) => {
      await gotoOffice(page, date, office);
      // Wait for scripture to load (replaces placeholder)
      await page.waitForSelector('.scripture-placeholder:not(:has(.loading))', { timeout: 10000 });
      // The reading-response tab strip is the .alt-block whose own tab strip
      // carries data-key="pwc-alt-reading_response" — scope with a direct-child
      // :has() so the match is the block itself, not an ancestor. A page-wide
      // filter would also catch: other alt-blocks (collect, canticle,
      // affirmation) via text overlap, and — since the reading selector (ADR
      // 0014/#63) wraps each lesson in its own outer .alt-block — that outer
      // wrapper too, since `has` without a combinator matches any descendant.
      const rrBlock = page.locator('.alt-block:has(> .alt-tabs > .alt-tab[data-key="pwc-alt-reading_response"])').first();
      await expect(rrBlock.locator('.alt-tabs')).toBeVisible();
      // Must have 3 options (I / II / III)
      await expect(rrBlock.locator(':scope > .alt-tabs > .alt-tab')).toHaveCount(3);
    });
  }
});

test("Lord's Prayer present in ordinary-time office", async ({ page }) => {
  await gotoOffice(page, '2026-06-17', 'mp');
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
      await gotoOffice(page, date, 'mp');
      await page.locator('#day-title').waitFor({ timeout: 5000 });
      await expect(page.locator('html')).toHaveAttribute('data-season', season);
    });
  }
});

// ── Typography ────────────────────────────────────────────────────────────────

// The Latin subsets in web/assets/fonts/ are built without `smcp`/`c2sc`
// (pyftsubset drops non-default layout features), so `font-variant: small-caps`
// against the reading face is browser-synthesized — caps scaled to 0.7em in
// Blink/WebKit, 0.8em in Gecko — rather than drawn. Synthesis looks plausible
// in isolation and only reveals itself next to the real thing, so nothing but
// an explicit check catches a regression here: heads would keep rendering,
// just wrongly. 'EB Garamond SC' carries both features for the head selectors.
test.describe('Small caps', () => {
  test('the SC face loads and the heads actually use it', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    await page.locator('.office-section-title').first().waitFor({ timeout: 5000 });
    await page.evaluate(() => document.fonts.ready);

    // The face resolves — not merely declared, but loaded and usable.
    const loaded = await page.evaluate(() =>
      document.fonts.check("600 1.3rem 'EB Garamond SC'"));
    expect(loaded, "'EB Garamond SC' should be loaded").toBe(true);

    // …and the selectors that set small caps resolve to it rather than the
    // reading face. Only the section head and the alternatives pills do now:
    // upstream review asked for rank by case, so a subcomponent head is set
    // upper-and-lower in the reading face and must NOT reach this family.
    for (const sel of ['.office-section-title', '.alt-tab']) {
      const family = await page.locator(sel).first()
        .evaluate(el => getComputedStyle(el).fontFamily);
      expect(family, `${sel} should use the SC face`).toContain('EB Garamond SC');
    }
    const subFamily = await page.locator('.office-subsection-title').first()
      .evaluate(el => getComputedStyle(el).fontFamily);
    expect(subFamily, 'a subcomponent head is not small caps').not.toContain('EB Garamond SC');
  });

  test('leaf text sizes resolve from their own tokens, not from body', async ({ page }) => {
    // body font-size is 1rem, but nothing inherits it — every text-bearing leaf
    // sets its own --fs-* / rem size (or inherits from a sized parent). These
    // three leaves are chosen to differ from body's 16px, so a future change
    // that makes one inherit body's size moves its computed value and this test
    // catches it. (The 1.1875rem → 1rem change was a verified no-op; this pins
    // the invariant that made it one.)
    await gotoOffice(page, DATE, 'mp');
    await page.locator('.office-section-title').first().waitFor({ timeout: 5000 });

    const sizeOf = (sel) => page.locator(sel).first()
      .evaluate(el => parseFloat(getComputedStyle(el).fontSize));

    // rem resolves against the root (html), which grows to 125% at the ≥820px
    // breakpoint, so expectations must scale with the measured root rather than
    // assume 16px. The invariant being pinned: each leaf equals its own rem
    // token × root, and inherits nothing from body.
    const root = await page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
    const remPx = (rem) => rem * root;

    // A nav link inherits .nav-row's 0.85rem, not body's 1rem.
    expect(await sizeOf('#nav a'), 'nav link should be 0.85rem').toBeCloseTo(remPx(0.85), 1);
    // A day-meta label sits on #day-meta's --fs-ui (0.8rem).
    expect(await sizeOf('.meta-item--season'), 'meta label should be 0.8rem').toBeCloseTo(remPx(0.8), 1);
    // A liturgy segment uses --fs-liturgy (1.1rem).
    expect(await sizeOf('.seg-leader'), 'segment should be 1.1rem').toBeCloseTo(remPx(1.1), 1);
  });
});

// ── Psalm verse layout ────────────────────────────────────────────────────────

// web/app.js renderPsalm is a second consumer of formatLiturgicalText and is not
// reachable from the Vitest suite, so three regressions shipped past a green unit
// run and only showed in a browser: markup spliced into the text by bindMidpoints,
// an empty line box per verse from a <br> join between block boxes, and the verse
// number stranded on a line above its own text.
//
// Deliberately NOT the module-wide DATE. The splice only fires when a line's whole
// content before the * is one word, so the greedy backtrack reaches through the
// tag's '>' with no intervening whitespace. Every line of Psalm 66/67 (DATE's MP)
// has several words before its *, so that fixture cannot catch it. 2026-11-29 MP
// is Psalms 146-147, and 146 opens "Hallelujah! *" — the shape that broke.
const PSALM_SPLICE_DATE = '2026-11-29';

test.describe('Psalm verses', () => {
  test('render one block per verse, number inline, no markup leak', async ({ page }) => {
    await gotoOffice(page, PSALM_SPLICE_DATE, 'mp');
    await waitForContentLoaded(page);
    const block = page.locator('.psalm-block').first();
    await expect(block).toBeVisible();

    // Guard the fixture itself: if the lectionary moves and this psalm stops
    // being the one with a one-word starred line, say so rather than pass blindly.
    await expect(block, 'fixture no longer exercises the splice case')
      .toContainText('Hallelujah!');

    // 1. No tag fragment survives as visible text.
    const text = await block.innerText();
    expect(text).not.toContain('class=');
    expect(text).not.toContain('verse-line');

    // 2. No <br>: the lines are block boxes already, and a <br> between two of
    //    them adds a full empty line box between every verse.
    await expect(block.locator('br')).toHaveCount(0);

    // 3. Each verse number shares a line with the text it numbers. Measured by
    //    vertical overlap of the number's box with the first line-box of the text
    //    that follows it — a Range, because the text after <sup> is usually a bare
    //    text node with no getBoundingClientRect of its own. A stranded number sits
    //    in its own line box and cannot overlap.
    const stranded = await block.evaluate(el => {
      const bad = [];
      el.querySelectorAll('sup').forEach(s => {
        const line = s.closest('.verse-line, .psalm-verse');
        if (!line) { bad.push(s.textContent.trim() + ':no-line'); return; }
        const sr = s.getBoundingClientRect();
        const r = document.createRange();
        r.setStartAfter(s);
        r.setEnd(line, line.childNodes.length);
        const first = r.getClientRects()[0];
        if (!first) { bad.push(s.textContent.trim() + ':no-text'); return; }
        if (!(first.top < sr.bottom && first.bottom > sr.top)) {
          bad.push(`${s.textContent.trim()}:sup[${sr.top.toFixed(0)}-${sr.bottom.toFixed(0)}] text[${first.top.toFixed(0)}-${first.bottom.toFixed(0)}]`);
        }
      });
      return bad;
    });
    expect(stranded, 'verse numbers not sharing a line with their text').toEqual([]);
  });
});

// ── Eves, day markers, and source notes ──────────────────────────────────────

// 2026-08-14 carries all three facts on one day: a commemoration, a fast, and
// an eve that takes the evening. Its note is the calendar compiler's apparatus.
const EVE_DATE = '2026-08-14';

test.describe('Eve identity (#128)', () => {
  test('evening prayer presents the eve, not the commemoration', async ({ page }) => {
    await gotoOffice(page, EVE_DATE, 'ep');
    await expect(page.locator('#day-title')).toHaveText('Eve of Saint Mary the Virgin');
    await expect(page).toHaveTitle(/Eve of Saint Mary the Virgin/);
    // The eve's colour, not the commemoration's green.
    await expect(page.locator('#day-meta .colour-name')).toHaveText('White');
    await expect(page.locator('#day-meta')).toContainText('Eve');
  });

  test('morning prayer keeps the commemoration whose propers it prays', async ({ page }) => {
    await gotoOffice(page, EVE_DATE, 'mp');
    await expect(page.locator('#day-title')).toContainText('Bonhoeffer');
    await expect(page.locator('#day-meta .colour-name')).toHaveText('Green');
    await expect(page.locator('#day-meta')).toContainText('Commemoration');
  });

  test('the header names the eve in the name column\'s full form', async ({ page }) => {
    // The office column abbreviates it to "Eve of Saint Mary", which stays
    // where the source put it — above the readings.
    await gotoOffice(page, EVE_DATE, 'ep');
    await expect(page.locator('#day-title')).toHaveText('Eve of Saint Mary the Virgin');
    await expect(page.locator('.observance-label')).toHaveText('Eve of Saint Mary');
  });

  test('the observance toggle names the primary slot as the title does', async ({ page }) => {
    // 2026-01-03: the day is Christmas Feria, the primary evening office is
    // the Eve of the Epiphany, and both toggle buttons are eves.
    await gotoOffice(page, '2026-01-03', 'ep');
    await expect(page.locator('#day-title')).toHaveText('Eve of the Epiphany');
    const obs = page.locator('.day-ctrl-seg--obs .day-ctrl-btn');
    await expect(obs).toHaveCount(2);
    await expect(obs.first()).toHaveText('Eve of the Epiphany');
  });
});

test.describe('Commemoration collect (#135)', () => {
  // The book names the day's collect and the commemoration's; the app kept
  // only the leading page, so a day ranked a Commemoration offered the
  // season's collect alone.
  test('the commemoration collect is offered beside the day\'s', async ({ page }) => {
    await gotoOffice(page, '2025-12-03', 'mp');   // "268 (Com: 434 or FAS 361)"
    const tabs = page.locator('#prayers-collect .alt-tab');
    await expect(tabs.filter({ hasText: 'Common of a Missionary' })).toHaveCount(1);
  });

  test('a slashed page offers both facing collects', async ({ page }) => {
    await gotoOffice(page, '2025-12-04', 'mp');   // "268 (Com: 438/9 or FAS 363)"
    const tabs = page.locator('#prayers-collect .alt-tab');
    await expect(tabs.filter({ hasText: 'Common of a Saint 1' })).toHaveCount(1);
    await expect(tabs.filter({ hasText: 'Common of a Saint 2' })).toHaveCount(1);
  });

  test('a day commemorating two people says whose collect is whose', async ({ page }) => {
    await gotoOffice(page, '2026-10-30', 'mp');
    const tabs = page.locator('#prayers-collect .alt-tab');
    await expect(tabs.filter({ hasText: 'Wyclyf: Common of a Saint 1' })).toHaveCount(1);
    await expect(tabs.filter({ hasText: 'Hus: Common of Doctors' })).toHaveCount(1);
  });

  test('selecting one shows that collect, not the day\'s', async ({ page }) => {
    await gotoOffice(page, '2026-10-30', 'mp');
    await page.locator('#prayers-collect .alt-tab')
      .filter({ hasText: 'Hus: Common of Doctors' }).click();
    await expect(page.locator('#prayers-collect .alt-source:visible').first())
      .toHaveText('Common of Doctors and Teachers of the Faith');
  });

  test('a day with no commemoration gains no tab', async ({ page }) => {
    // 2025-12-02 is an Advent feria — collect "268", no parenthetical at all.
    await gotoOffice(page, '2025-12-02', 'mp');
    await expect(page.locator('#prayers-collect .alt-tab').filter({ hasText: 'Common of' }))
      .toHaveCount(0);
  });
});

test.describe('Co-commemoration (#129)', () => {
  // 2026-10-30 names two commemorations of equal standing. Naming one of them
  // in the title would be the app choosing a day for the reader (ADR 0016).
  test('two co-equal commemorations are both named in the title', async ({ page }) => {
    await gotoOffice(page, '2026-10-30', 'mp');
    await expect(page.locator('#day-title'))
      .toHaveText('John Wyclyf, Reformer, 1384 or Jan Hus, Reformer, 1415');
  });

  test('each co-commemorated saint has their own biography', async ({ page }) => {
    await gotoOffice(page, '2026-10-30', 'mp');
    await expect(page.locator('.fats-bio-toggle')).toHaveText([
      'About John Wyclyf, Reformer, 1384',
      'About Jan Hus, Reformer, 1415',
    ]);
  });

  // A commemoration kept under a Holy Day is subordinate, not a second title.
  test('a commemoration under a holy day is a marker, not a title', async ({ page }) => {
    await gotoOffice(page, '2025-12-29', 'mp');
    await expect(page.locator('#day-title')).toHaveText('The Holy Innocents');
    await expect(page.locator('#day-meta'))
      .toContainText('Thomas Becket, Archbishop of Canterbury, 1170');
  });

  test('a subordinate commemoration still reaches its biography', async ({ page }) => {
    await gotoOffice(page, '2025-12-29', 'mp');
    await expect(page.locator('.fats-bio-toggle'))
      .toContainText(['The Holy Innocents', 'Thomas Becket, Archbishop of Canterbury, 1170']);
  });

  // #137: the calendar writes this pair on one line, joined by "and", where
  // the other co-commemorations get a line each.
  test('a pair written inline on one line is named as two', async ({ page }) => {
    await gotoOffice(page, '2026-10-15', 'mp');
    await expect(page.locator('#day-title')).toHaveText(
      'Teresa of Avila, Spiritual Teacher and Reformer, 1582 and '
      + 'John of the Cross, Priest, Spiritual Teacher, 1591');
    await expect(page.locator('.fats-bio-toggle')).toHaveText([
      'About Teresa of Avila, Spiritual Teacher and Reformer, 1582',
      'About John of the Cross, Priest, Spiritual Teacher, 1591',
    ]);
  });

  test('the header carries no rank marker from the source', async ({ page }) => {
    await gotoOffice(page, '2026-10-15', 'mp');
    await expect(page.locator('#day-title')).not.toContainText('- Com');
  });

  test('a day naming one observance is unchanged', async ({ page }) => {
    await gotoOffice(page, '2026-08-13', 'mp');
    await expect(page.locator('#day-meta .meta-item--marker')).toHaveCount(0);
  });
});

test.describe('Day markers (#128)', () => {
  test('the fast shows on both offices', async ({ page }) => {
    await gotoOffice(page, EVE_DATE, 'mp');
    await expect(page.locator('#day-meta')).toContainText('Day of discipline and self-denial');
    await ensureOffice(page, 'ep');
    await expect(page.locator('#day-meta')).toContainText('Day of discipline and self-denial');
  });

  test('each office names the other\'s day', async ({ page }) => {
    // The eve is a fact about the calendar day, so the morning says so; the
    // evening, having taken the eve as its title, names the commemoration.
    await gotoOffice(page, EVE_DATE, 'mp');
    await expect(page.locator('#day-meta')).toContainText('Eve of Saint Mary the Virgin');
    await ensureOffice(page, 'ep');
    await expect(page.locator('#day-meta')).toContainText('Bonhoeffer');
  });

  test('a day with neither gets no markers', async ({ page }) => {
    await gotoOffice(page, '2026-08-13', 'mp');
    await expect(page.locator('#day-meta .meta-item--marker')).toHaveCount(0);
  });
});

test.describe('Source notes (#127)', () => {
  test('apparatus is behind a closed disclosure, not in the reading flow', async ({ page }) => {
    await gotoOffice(page, EVE_DATE, 'mp');
    const det = page.locator('.day-note-details');
    await expect(det).toHaveCount(1);
    await expect(det).not.toHaveAttribute('open', '');
    await expect(det.locator('summary')).toHaveText('About these readings');
    // Not rendered as a pastoral note.
    await expect(page.locator('.day-note')).toHaveCount(0);
  });

  test('opening it shows the note and glosses DOL', async ({ page }) => {
    await gotoOffice(page, EVE_DATE, 'mp');
    await page.locator('.day-note-details summary').click();
    await expect(page.locator('.day-note-details-body')).toContainText('two sets of readings');
    await expect(page.locator('.day-note-gloss')).toContainText('Daily Office Lectionary');
  });

  test('a rule fused with its sourcing no longer suppresses it', async ({ page }) => {
    // 2026-06-28 held both in one cell; typing the cell as a whole hid both.
    await gotoOffice(page, '2026-06-28', 'ep');
    await page.locator('.day-note-details summary').click();
    const body = page.locator('.day-note-details-body');
    await expect(body).toContainText('The readings provided are found in the BCP');
    // The precedence rule stays suppressed — it is applied, not advisory.
    await expect(body).not.toContainText('takes precedence');
  });

  test('a cell of mixed kinds splits by kind', async ({ page }) => {
    // 2026-01-06: an apparatus note and an actionable office note.
    await gotoOffice(page, '2026-01-06', 'mp');
    await expect(page.locator('.day-note-details-body p').first())
      .toContainText('always kept as the Epiphany');
    await expect(page.locator('.day-note')).toContainText('Office Note');
  });

  test('pastoral customs still render in the open', async ({ page }) => {
    await gotoOffice(page, '2026-12-13', 'mp');
    await expect(page.locator('.day-note')).toContainText('Gaudete');
    await expect(page.locator('.day-note-details')).toHaveCount(0);
  });
});
