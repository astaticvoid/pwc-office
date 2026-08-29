// @ts-check
import { readFileSync } from 'fs';
import { join } from 'path';
import { test, expect } from '@playwright/test';
import { gotoOffice, ensureOffice, openDatePicker } from './helpers.js';
import { richDay, daysNamed, shiftDate, findDay, extremeDay, dayOf, officeOf, seasonFor, partialPsalmDay } from './days.js';
import { parsePsalmCitation } from '../../web/render.js';

// A day with structure to exercise rather than today, whose shape is whatever
// the calendar happens to give: an alternate observance in both offices, two
// lessons in each, and a pastoral note long enough to expand. Asked for by
// those properties rather than named, so the rolling window cannot drop it
// (#141).
const DATE      = richDay();
const DATE_PREV = shiftDate(DATE, -1);
const DATE_NEXT = shiftDate(DATE, +1);

// Days named by the shape that makes them the case under test (#141).
const twoNamedCollects = () => findDay(
  'a day whose collect ref names a page per commemorated person',
  d => ((d.morning?.collect || '').match(/\(Com \w+:/g) || []).length >= 2);
const namesInCollectRef = date =>
  [...officeOf(date, 'mp').collect.matchAll(/\(Com (\w+):/g)].map(m => m[1]);
const coequalDay = () => findDay(
  'a day whose commemoration is co-equal with the day itself',
  d => (d.commemorations || []).some(c => c.coequal));
const subordinateDay = () => findDay(
  'a holy day keeping a commemoration under it rather than beside it',
  d => d.rank === 'holy_day' && (d.commemorations || []).some(c => !c.coequal));
const ordinaryTimeDay = () => findDay(
  'a feria in Ordinary Time',
  d => d.morning && d.rank === 'feria' && seasonFor(d.date) === 'OrdinaryTime');
const inlinePairDay = () => findDay(
  'a day whose calendar line joins its co-equal pair with "and"',
  d => (d.commemorations || []).some(c => c.coequal) && d.commemoration_join === 'and');
const plainDay = () => findDay(
  'an ordinary commemorated day with nothing else to mark — no second name, no fast, no eve',
  d => d.morning && !d.commemorations && !(d.observances || []).length
    && ['memorial', 'commemoration'].includes(d.rank));

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
    await expect(page.locator('.day-ctrl-group--office .day-ctrl-btn:text-is("Morning Prayer")')).toHaveAttribute('aria-pressed', 'true');
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

  test('a single untabbed psalm citation shows its verse range in the heading', async ({ page }) => {
    // #162: psalmHtml only puts a citation on a tab label when there's more
    // than one psalm to choose between — for a single partial-range psalm
    // (no tab), the in-content heading is the only place the range can show,
    // or the reader has no way to know they aren't seeing the whole psalm.
    const { date, office } = partialPsalmDay();
    const citation = officeOf(date, office).psalms[0];
    const cit = typeof citation === 'object' ? citation.citation : citation;
    const [, start, end] = /^\d+:(\d+)-?(\d+)?$/.exec(cit);
    await gotoOffice(page, date, office);
    const title = page.locator('.psalm-title').first();
    await expect(title).toBeVisible({ timeout: CONTENT_TIMEOUT });
    await expect(title).toContainText(`:${start}${end ? `-${end}` : ''}`);
    // The verse content itself must actually start where the heading claims.
    await expect(page.locator('.psalm-block sup').first()).toHaveText(start);
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
    // Both readings stay in the office in book order, no per-reading selector
    // (ADR 0019 item 7, #77) — so each of the 2 lessons' 3 response tabs
    // renders once: 3 × 2 = 6.
    await expect(responseTabs).toHaveCount(6);
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
// in the day header (.day-ctrl-group--office) — its active button is the only
// indicator of the current office; there is no separate label.
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

    await expect(page.locator('.day-ctrl-group--office .day-ctrl-btn.is-active'))
      .toHaveText('Evening Prayer');
    await expect(page.locator('.day-ctrl-group--obs .day-ctrl-btn.is-active'))
      .toHaveText(String(altLabel));

    // and back the other way: flipping observance keeps the office
    await page.locator('.day-ctrl-group--obs .day-ctrl-btn').nth(0).click();
    await expect(page.locator('.day-ctrl-group--office .day-ctrl-btn.is-active'))
      .toHaveText('Evening Prayer');
  });

  // The Opening control lives with the other header controls: which opening the
  // office uses is decided at the time of prayer, not behind a sheet (#165).
  // The Penitential Office fronts the Gathering and the service still continues
  // with the Introductory Responses; the choice survives an office switch and
  // flips back to Standard just as cleanly.
  test('the Opening selector swaps in the Penitential Office', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp');
    const content = page.locator('#office-content');
    await expect(content).not.toContainText('Let us confess our sins');

    const opening = page.locator('.day-ctrl-group--opening');
    await expect(opening).toBeVisible();
    await expect(opening.locator('.day-ctrl-btn.is-active')).toHaveText('Standard');

    await opening.locator('.day-ctrl-btn:text-is("Penitential")').click();
    await expect(content).toContainText('A Penitential Office');
    await expect(content).toContainText('Let us confess our sins against God and our neighbour.');
    await expect(content).toContainText('May the God of love and power');
    await expect(content).toContainText('continues with the Introductory Responses');
    // the confession/absolution choices use the app's own I/II pill tabs —
    // the first two tab pills belong to the confession
    await expect(content.locator('.alt-tab').nth(0)).toHaveText('I');
    await expect(content.locator('.alt-tab').nth(1)).toHaveText('II');
    // the standard service still follows the penitential opening
    await expect(content).toContainText('O Lord, open our lips');

    // the choice survives an office switch (it is state, not a date property)
    await page.locator('.day-ctrl-group--office .day-ctrl-btn:text-is("Evening Prayer")').click();
    await expect(opening.locator('.day-ctrl-btn.is-active')).toHaveText('Penitential');
    await expect(content).toContainText('May the God of love and power');

    await opening.locator('.day-ctrl-btn:text-is("Standard")').click();
    await expect(content).not.toContainText('Let us confess our sins');
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
    // ordinary-saturday-mp is the form carrying the long canticle name, and a
    // Saturday reaches it only in Ordinary Time.
    const date = findDay('a feria Saturday in Ordinary Time', d =>
      new Date(d.date + 'T12:00:00Z').getUTCDay() === 6 && d.rank === 'feria'
      && d.morning && seasonFor(d.date) === 'OrdinaryTime');
    await page.setViewportSize({ width: 320, height: 800 });
    await gotoOffice(page, date, 'mp');

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
    const date = findDay('an evening offering two alternative psalm sets, the second a single psalm',
      d => (d.evening?.psalm_sets || []).length === 2 && d.evening.psalm_sets[1].length === 1);
    const sets = officeOf(date, 'ep').psalm_sets;
    await gotoOffice(page, date, 'ep');
    const psalmBlock = page.locator('.alt-block:has(> .alt-tabs > .alt-tab[data-key^="pwc-psalmset-"])').first();
    await psalmBlock.waitFor();
    const tabs = psalmBlock.locator(':scope > .alt-tabs > .alt-tab');
    await expect(tabs).toHaveCount(sets.length + 1); // All, then one per set
    await expect(tabs.nth(0)).toHaveText('All');
    await expect(tabs.nth(0)).toHaveClass(/alt-tab-active/);

    // Selecting the second set isolates it: its panel shows, the others hide.
    await tabs.nth(2).click();
    await expect(psalmBlock.locator(':scope > .alt-panel').nth(0)).toHaveClass(/alt-panel-hidden/);
    await expect(psalmBlock.locator(':scope > .alt-panel').nth(2)).not.toHaveClass(/alt-panel-hidden/);
    const soleCitation = typeof sets[1][0] === 'object' ? sets[1][0].citation : sets[1][0];
    await expect(psalmBlock.locator(':scope > .alt-panel').nth(2)
      .locator(`[data-citation="${soleCitation}"]`)).toHaveCount(1);
  });

  test('multiple plain psalms renders an All + one-tab-per-psalm selector', async ({ page }) => {
    const date = findDay('an evening appointing exactly two plain psalms',
      d => !d.evening?.psalm_sets && (d.evening?.psalms || []).length === 2);
    const psalms = officeOf(date, 'ep').psalms;
    await gotoOffice(page, date, 'ep');
    const psalmBlock = page.locator('.alt-block:has(> .alt-tabs > .alt-tab[data-key^="pwc-psalm-"])').first();
    await psalmBlock.waitFor();
    const tabs = psalmBlock.locator(':scope > .alt-tabs > .alt-tab');
    await expect(tabs).toHaveCount(psalms.length + 1); // All, then one per psalm
    await expect(tabs.nth(1)).toHaveText(`Psalm ${psalms[0]}`);
    await expect(tabs.nth(2)).toHaveText(`Psalm ${psalms[1]}`);

    await tabs.nth(1).click();
    const panel1 = psalmBlock.locator(':scope > .alt-panel').nth(1);
    await expect(panel1).not.toHaveClass(/alt-panel-hidden/);
    // Individual panel is self-contained: just the one psalm, not the other.
    await expect(panel1.locator(`[data-citation="${psalms[0]}"]`)).toHaveCount(1);
    await expect(panel1.locator(`[data-citation="${psalms[1]}"]`)).toHaveCount(0);
  });

  test('multiple readings stay in book order with no selector', async ({ page }) => {
    await gotoOffice(page, DATE, 'mp'); // richDay(): two lessons per office
    // The choice between readings is carried by rubrics, not a control that
    // could remove the Responsory or the Canticle from a per-reading view
    // (ADR 0019 item 7, #77) — so no reading tab strip exists at all.
    await expect(page.locator('.alt-tab[data-key^="pwc-reading-"]')).toHaveCount(0);

    const primary = page.locator('.obs-readings[data-obs="primary"]');
    await expect(primary.locator('.reading-heading')).toHaveCount(2);
    await expect(primary.locator('.office-subsection-title', { hasText: 'Responsory' })).toHaveCount(1);
    await expect(primary.locator('.office-subsection-title', { hasText: 'Canticle' })).toHaveCount(1);

    // Book order: lesson 1 → Responsory → lesson 2 → Canticle.
    const items = await primary.locator('.reading-heading, .office-subsection-title').evaluateAll(
      els => els.map(el => ({ isReading: el.classList.contains('reading-heading'), text: el.textContent }))
    );
    const order = items.filter(i => i.isReading || /Responsory|Canticle/.test(i.text));
    expect(order).toHaveLength(4);
    expect(order[0].isReading).toBe(true);
    expect(order[1].text).toContain('Responsory');
    expect(order[2].isReading).toBe(true);
    expect(order[3].text).toContain('Canticle');
    // The first reading sits right under the "The Reading" subsection title,
    // so its own heading is just the citation (#158); the second has no
    // subsection title of its own and keeps the full "The Reading: " prefix.
    expect(order[0].text).not.toMatch(/^The Reading:/);
    expect(order[2].text).toMatch(/^The Reading:/);
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
    // A day whose alternate states a rank of its own, differing from the day's,
    // so the chip has something to follow.
    const date = findDay('a holy day whose morning alternate is the feria, ranked as such',
      d => d.rank === 'holy_day' && d.morning?.alternate?.rank === 'feria');
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('#day-meta')).toContainText('Holy Day', { timeout: 5000 });
    await expect(page.locator(OBS_ALT)).toBeVisible({ timeout: 5000 });
    await page.locator(OBS_ALT).click();
    await expect(page.locator('#day-meta')).toContainText('Feria', { timeout: 5000 });
  });

  // #132: a rubric standing where a branch's name would stand is set as a
  // rubric. The observance caption is small spaced capitals, which is a
  // reasonable setting for "Feria" and not for a sentence.
  test('a rubric heading an office is set as a rubric, not as an observance name', async ({ page }) => {
    // The one office in the window whose branch is headed by a rubric rather
    // than a name — a sentence standing where an observance label would.
    const date = findDay('an evening headed by a rubric rather than an observance name',
      d => /^This office is only to be used/.test(d.evening?.rubric || ''));
    await gotoOffice(page, date, 'ep');
    const rubric = page.locator('.office-rubric');
    await expect(rubric).toHaveText(dayOf(date).evening.rubric);
    await expect(page.locator('.observance-label')).toHaveCount(0);
    await expect(rubric).toHaveCSS('text-transform', 'none');
  });

  // ADR 0018 as amended (#133): an alternate the name column never identifies
  // shows no colour or rank rather than the primary's. The season stays — it
  // is a fact about the date, not about the observance.
  test('an alternate with no identity of its own shows no colour or rank', async ({ page }) => {
    // A holy day whose alternate the name column never identifies: it carries
    // a label and nothing else, so there is no colour or rank to show.
    const date = findDay('a holy day whose alternate states neither colour nor rank',
      d => d.rank === 'holy_day' && d.colour && d.morning?.alternate
        && !d.morning.alternate.colour && !d.morning.alternate.rank);
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('#day-meta')).toContainText('Holy Day', { timeout: 5000 });
    await expect(page.locator('#day-meta .colour-name')).toHaveText(dayOf(date).colour);

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
    // The longest name the window carries, whatever it is: the point is that
    // length does not truncate it.
    const date = extremeDay('a day with an alternate observance',
      d => d.morning?.alternate && d.name, d => d.name.length);
    await gotoOffice(page, date, 'mp');
    const primary = page.locator('.day-ctrl-seg--obs .day-ctrl-btn').first();
    await expect(primary).toHaveText(dayOf(date).name);
  });

  // Writing the name out costs nothing if the segment then leaves the column:
  // above the 820px step the control group is sized by its content, so the
  // segment's own max-width has to be clamped against something narrower.
  test('the segment stays inside the header column and keeps its 44px target', async ({ page }) => {
    // Both sides long, so the segment is under the most pressure the data offers.
    const date = extremeDay('an evening with an alternate observance',
      d => d.evening?.alternate?.label && d.name,
      d => d.name.length + d.evening.alternate.label.length);
    await gotoOffice(page, date, 'ep');
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

  // An eve/feast alternate names no person, so selecting it must clear the
  // primary day's biography rather than keeping it — the bio follows who is
  // being prayed, not the calendar day alone. Found by property: a day whose
  // own name has a FATS life and whose evening offers an alternate.
  test("an eve/feast alternate clears the day's biography", async ({ page }) => {
    const fats = JSON.parse(readFileSync(join(import.meta.dirname, '../..', 'data/fats/saints.json'), 'utf8'));
    const keys = new Set(Object.keys(fats).map(k => k.toLowerCase()));
    const date = findDay(
      'a day whose own name has a biography and whose evening offers an alternate',
      d => d.evening?.alternate && keys.has((d.name || '').toLowerCase()));
    await gotoOffice(page, date, 'ep');
    await expect(page.locator('.fats-bio').first()).toBeVisible();
    const before = await page.locator('.fats-bio').count();
    expect(before).toBeGreaterThanOrEqual(1);
    await page.locator('.day-ctrl-seg--obs .day-ctrl-btn').nth(1).click();
    await expect(page.locator('.fats-bio')).toHaveCount(0);
  });
});

// ── Section shapes the renderer depends on ───────────────────────────────────

test.describe('Reading response renders after lesson', () => {
  // One of each: the seasonal forms and the weekday forms carry their own
  // reading-response block, so a day from each season proves both.
  for (const [label, date, office] of [
    ['seasonal (Lent)', findDay('a day in Lent', d => d.morning && seasonFor(d.date) === 'Lent'), 'mp'],
    ['ordinary-time', ordinaryTimeDay(), 'mp'],
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
  await gotoOffice(page, ordinaryTimeDay(), 'mp');
  await expect(page.locator('.office-subsection-title', { hasText: "The Lord's Prayer" })).toBeVisible();
});

// ── Season theming (JS/Go parity) ────────────────────────────────────────────
// These boundary dates must agree with TestFormSeasonOf in season_test.go.
// A failure here means seasonOf() or officeFormSeason() in app.js has drifted
// from the Go implementations in season.go.

test.describe('Season theming parity', () => {
  // Each case is a day the calendar names, so it recurs and the window always
  // holds one. Advent I and Christmas Day appear twice — first and last — which
  // is the point of those two: the season must be read the same either side of
  // the liturgical new year.
  const advent = daysNamed(/^First Sunday of Advent$/);
  const christmas = daysNamed(/Christmas Day$/);
  const cases = [
    // data-season is set by seasonOf() in app.js
    { date: advent[0],                       season: 'Advent',      label: 'Advent I' },
    { date: christmas[0],                    season: 'Christmas',   label: 'Christmas Day' },
    { date: daysNamed(/^The Baptism of the Lord$/)[0],   season: 'Epiphany',    label: 'Baptism of the Lord' },
    { date: daysNamed(/^Ash Wednesday$/)[0],             season: 'Lent',        label: 'Ash Wednesday' },
    { date: daysNamed(/^Fifth Sunday in Lent$/)[0],      season: 'Passiontide', label: '5th Sunday in Lent' },
    { date: daysNamed(/Easter Day$/)[0],                 season: 'Easter',      label: 'Easter Day' },
    // Ascension: seasonOf uses Pentecost as season boundary (not Ascension)
    { date: daysNamed(/^Ascension of the Lord$/)[0],     season: 'Easter',      label: 'Ascension — still Easter theme' },
    { date: daysNamed(/^The Day of Pentecost$/)[0],      season: 'Pentecost',   label: 'Pentecost Sunday' },
    { date: daysNamed(/^All Saints/)[0],                 season: 'AllSaints',   label: 'All Saints' },
    { date: advent[advent.length - 1],        season: 'Advent',      label: 'Advent I (the next year)' },
    { date: christmas[christmas.length - 1],  season: 'Christmas',   label: 'Christmas Day (the next year)' },
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
// reachable from the Vitest suite, so renderer regressions only show in a browser:
// markup spliced into the text, an empty line box per verse from a <br> join
// between block boxes, and the verse number stranded on a line above its own text.
//
// Deliberately NOT the module-wide DATE. A one-word line before the * exercises
// the midpoint transform on the first line of a verse, immediately after the
// verse-number prefix (Psalm 146 opens "Hallelujah! *"). Every line of Psalm 66/67
// (DATE's MP) has several words before its *, so that fixture cannot catch it.
const PSALM_SPLICE_DATE = findDay(
  'a morning appointing Psalm 146, which opens "Hallelujah! *"',
  d => (d.morning?.psalms || []).some(x => (typeof x === 'object' ? x.citation : x) === '146'));

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

// A merged citation's `omit` span is read off the CSV, not off the psalter —
// so it can name a verse the psalter itself does not reach (data/psalter.json's
// numbering does not always run as far as the citation's nominal end).
// Bracketing on the citation's own numbers would then open a '[' with no
// verse left to carry the matching ']' (#78).
const PSALTER = JSON.parse(readFileSync(join(import.meta.dirname, '../../data/psalter.json'), 'utf8'));
function psalmMaxVerse(num) {
  const nums = [...(PSALTER[String(num)]?.text || '').matchAll(/^(\d+)\s/gm)].map(m => parseInt(m[1]));
  return nums.length ? Math.max(...nums) : 0;
}
const OVERREACHING_OMIT = (() => {
  for (const office of ['morning', 'evening']) {
    const date = findDay(
      `an ${office} office whose omit span names a verse beyond the psalm's own last verse`,
      d => (d[office]?.psalms || []).some(p => {
        if (typeof p !== 'object' || !p.omit) return false;
        const { num } = parsePsalmCitation(p.citation);
        return p.omit.some(o => parsePsalmCitation(o.citation).end > psalmMaxVerse(num));
      }));
    if (date) return { date, office: office === 'morning' ? 'mp' : 'ep' };
  }
  throw new Error('no office in the published lectionary has an omit span beyond its psalm\'s last verse');
})();

test.describe('Psalm omit-range clamping (#78)', () => {
  test('a bracket never opens without closing, even when the citation omits past the psalm\'s own last verse', async ({ page }) => {
    await gotoOffice(page, OVERREACHING_OMIT.date, OVERREACHING_OMIT.office);
    await waitForContentLoaded(page);
    const text = (await page.locator('.psalm-block').allInnerTexts()).join('\n');
    const opens = (text.match(/\[/g) || []).length;
    const closes = (text.match(/\]/g) || []).length;
    expect(opens, 'fixture no longer exercises an overreaching omit span').toBeGreaterThan(0);
    expect(closes, 'unmatched brackets in rendered psalm text').toBe(opens);
  });
});

// ── Eves, day markers, and source notes ──────────────────────────────────────

// All three facts on one day: a commemoration, a fast, and an eve that takes
// the evening — the combination the markers have to keep apart.
const EVE_DATE = findDay(
  'a day carrying a commemoration, a fast, and an eve on its evening',
  d => (d.observances || []).includes('fast_day')
    && (d.observances || []).some(o => /^eve_of:/.test(o))
    && d.rank === 'commemoration');

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
    // An evening whose primary slot is an eve rather than the day itself, so
    // naming the slot after the day would name the wrong thing.
    const date = findDay('an evening whose primary slot is an eve, with an alternate beside it',
      d => /^Eve of /i.test(d.evening?.label || '') && d.evening?.alternate);
    await gotoOffice(page, date, 'ep');
    const title = page.locator('#day-title');
    await expect(title).toContainText(/^Eve of /);
    const obs = page.locator('.day-ctrl-seg--obs .day-ctrl-btn');
    await expect(obs).toHaveCount(2);
    // The two must say the same thing — which is the claim, and it holds
    // without either side being spelled out here.
    await expect(obs.first()).toHaveText((await title.textContent()).trim());
  });
});

test.describe('Commemoration collect (#135)', () => {
  // The book names the day's collect and the commemoration's; the app kept
  // only the leading page, so a day ranked a Commemoration offered the
  // season's collect alone.
  test('the commemoration collect is offered beside the day\'s', async ({ page }) => {
    // A day whose collect ref names a commemoration's collect beside the day's.
    const date = findDay("a day whose collect ref names a commemoration's collect",
      d => /^\d+ \(Com: \d/.test(d.morning?.collect || ''));
    await gotoOffice(page, date, 'mp');
    const tabs = page.locator('#prayers-collect .alt-tab');
    // Both are offered: the day's own and the one the ref names beside it.
    await expect(tabs.filter({ hasText: 'Common of' })).toHaveCount(1);
    await expect(tabs).toHaveCount(2);
  });

  test('a slashed page offers both facing collects', async ({ page }) => {
    // "438/9" abbreviates a facing page by its final digits, so the ref names
    // two collects where it looks like one.
    const date = findDay('a day whose commemoration ref abbreviates a facing page',
      d => /\(Com: \d+\/\d/.test(d.morning?.collect || ''));
    await gotoOffice(page, date, 'mp');
    const tabs = page.locator('#prayers-collect .alt-tab');
    await expect(tabs.filter({ hasText: 'Common of' })).toHaveCount(2);
  });

  test('a day commemorating two people says whose collect is whose', async ({ page }) => {
    const date = twoNamedCollects();
    const who = namesInCollectRef(date);
    await gotoOffice(page, date, 'mp');
    const tabs = page.locator('#prayers-collect .alt-tab');
    // The ref names the person against each page, and so must the tab. One
    // person can carry more than one tab: an abbreviated facing page ("438/9")
    // is two collects under the same name.
    for (const name of who) {
      await expect
        .poll(() => tabs.filter({ hasText: new RegExp(`^${name}: `) }).count())
        .toBeGreaterThan(0);
    }
  });

  test('selecting one shows that collect, not the day\'s', async ({ page }) => {
    const date = twoNamedCollects();
    const who = namesInCollectRef(date);
    await gotoOffice(page, date, 'mp');
    const source = page.locator('#prayers-collect .alt-source:visible').first();
    const tabFor = n => page.locator('#prayers-collect .alt-tab')
      .filter({ hasText: new RegExp(`^${n}: `) }).first();
    await tabFor(who[0]).click();
    const first = (await source.textContent()).trim();
    await tabFor(who[1]).click();
    // A different person's page is a different collect, not the day's again.
    await expect(source).not.toHaveText(first);
    await expect(source).not.toHaveText('');
  });

  test('a day with no commemoration gains no tab', async ({ page }) => {
    // A day whose collect ref is a bare page: nothing to offer beside it.
    const date = findDay('a day whose collect ref is a bare page number',
      d => /^\d+$/.test((d.morning?.collect || '').trim()));
    await gotoOffice(page, date, 'mp');
    // The assertion below is an absence, which an unrendered page satisfies
    // too. #day-title is written past every early return in render(), so it
    // holding this day's name is what says this day rendered — where "some
    // element is visible" is satisfied by the header gotoOffice already
    // painted for today, which nothing clears.
    await expect(page.locator('#day-title')).toHaveText(dayOf(date).name);
    await expect(page.locator('#prayers-collect .alt-tab').filter({ hasText: 'Common of' }))
      .toHaveCount(0);
  });
});

test.describe('Co-commemoration (#129)', () => {
  // 2026-10-30 names two commemorations of equal standing. Naming one of them
  // in the title would be the app choosing a day for the reader (ADR 0016).
  test('two co-equal commemorations are both named in the title', async ({ page }) => {
    await gotoOffice(page, coequalDay(), 'mp');
    await expect(page.locator('#day-title'))
      .toHaveText('John Wyclyf, Reformer, 1384 or Jan Hus, Reformer, 1415');
  });

  test('each co-commemorated saint has their own biography', async ({ page }) => {
    const date = coequalDay();
    const day = dayOf(date);
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('.fats-bio-toggle')).toHaveText(
      [day.name, ...day.commemorations.map(c => c.name)].map(n => `About ${n}`));
  });

  // A commemoration kept under a Holy Day is subordinate, not a second title.
  test('a commemoration under a holy day is a marker, not a title', async ({ page }) => {
    const date = subordinateDay();
    const day = dayOf(date);
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('#day-title')).toHaveText(day.name);
    await expect(page.locator('#day-meta')).toContainText(day.commemorations[0].name);
  });

  test('a subordinate commemoration still reaches its biography', async ({ page }) => {
    const date = subordinateDay();
    const day = dayOf(date);
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('.fats-bio-toggle'))
      .toContainText([day.name, day.commemorations[0].name]);
  });

  // #137: the calendar writes this pair on one line joined by "and", where the
  // other co-commemorations are offered as alternatives and joined by "or".
  // The title carries the source's own joiner (commemoration_join), so the day
  // is asked for by which joiner it uses.
  test('a pair written inline on one line is named as two', async ({ page }) => {
    const date = inlinePairDay();
    const day = dayOf(date);
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('#day-title'))
      .toHaveText(`${day.name} ${day.commemoration_join} ${day.commemorations[0].name}`);
    await expect(page.locator('.fats-bio-toggle')).toHaveText(
      [day.name, day.commemorations[0].name].map(n => `About ${n}`));
  });

  test('the header carries no rank marker from the source', async ({ page }) => {
    await gotoOffice(page, inlinePairDay(), 'mp');
    await expect(page.locator('#day-title')).not.toContainText('- Com');
  });

  test('a day naming one observance is unchanged', async ({ page }) => {
    const date = plainDay();
    await gotoOffice(page, date, 'mp');
    // Anchored on the day's own name: #day-meta is in the header, outside the
    // #office-content render() clears, so its presence says nothing about the
    // day under test.
    await expect(page.locator('#day-title')).toHaveText(dayOf(date).name);
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

  test('the bar\'s · trails a token only when another token follows', async ({ page }) => {
    // The separator is ::after, which text matching cannot see — read the
    // computed pseudo-content. A bar token trails its · only when another bar
    // token follows it; the last bar token and every marker carry none (#164).
    await gotoOffice(page, EVE_DATE, 'mp');
    const items = await page.locator('#day-meta .meta-item').evaluateAll(els =>
      els.map(el => ({
        marker: el.classList.contains('meta-item--marker'),
        after: getComputedStyle(el, '::after').content,
      })));
    expect(items.filter(i => i.marker).length).toBeGreaterThan(0);
    const lastBarIdx = items.map(i => i.marker).lastIndexOf(false);
    items.forEach((item, idx) => {
      if (item.marker) {
        expect(item.after, `marker ${idx} must not carry a ·`).toBe('none');
      } else if (idx === lastBarIdx) {
        expect(item.after, `last bar token ${idx} must not trail a ·`).toBe('none');
      } else {
        expect(item.after, `bar token ${idx} trails its ·`).toBe('"·"');
      }
    });
  });

  test('each office names the other\'s day', async ({ page }) => {
    // The eve is a fact about the calendar day, so the morning says so; the
    // evening, having taken the eve as its title, names the commemoration.
    await gotoOffice(page, EVE_DATE, 'mp');
    await expect(page.locator('#day-meta')).toContainText('Eve of Saint Mary the Virgin');
    await ensureOffice(page, 'ep');
    await expect(page.locator('#day-meta')).toContainText('Bonhoeffer');
  });

  test('the eve marker is dropped where the observance toggle already offers it', async ({ page }) => {
    // A day whose evening is both an eve and offers the eve as an alternate
    // (the June-6 configuration): the office toggle names the eve as a button,
    // so the meta row must not repeat it as a marker — the two would be
    // redundant. On the morning, which carries no alternate, the marker stays.
    const date = findDay(
      'a day whose evening is an eve and offers an alternate in the evening office',
      d => (d.observances || []).some(o => /^eve_of:/.test(o)) && !!d.evening?.alternate);
    // Primary selected (default): the toggle shows the eve, so no marker.
    await gotoOffice(page, date, 'ep');
    await expect(page.locator('.day-ctrl-seg--obs .day-ctrl-btn')).toHaveCount(2);
    await expect(page.locator('#day-meta')).not.toContainText(/Eve of/);
    // Morning has no alternate: the eve is a marker, not a button.
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('.day-ctrl-seg--obs')).toHaveCount(0);
    await expect(page.locator('#day-meta')).toContainText(/Eve of/);
  });

  test('a day with neither gets no markers', async ({ page }) => {
    const date = plainDay();
    await gotoOffice(page, date, 'mp');
    // Anchored on the day's own name: #day-meta is in the header, outside the
    // #office-content render() clears, so its presence says nothing about the
    // day under test.
    await expect(page.locator('#day-title')).toHaveText(dayOf(date).name);
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
    // A cell holding an advisory note and a precedence rule together: typing
    // the cell as a whole would let one kind decide the other's fate.
    const date = findDay('an evening whose notes carry both an advisory and a rule',
      d => (d.notes || []).some(n => /readings provided are found in the BCP/.test(n.text || '')));
    await gotoOffice(page, date, 'ep');
    await page.locator('.day-note-details summary').click();
    const body = page.locator('.day-note-details-body');
    await expect(body).toContainText('The readings provided are found in the BCP');
    // The precedence rule stays suppressed — it is applied, not advisory.
    await expect(body).not.toContainText('takes precedence');
  });

  test('a cell of mixed kinds splits by kind', async ({ page }) => {
    // A day whose notes are of two kinds at once: apparatus behind the
    // disclosure, an actionable office note in the open.
    const date = findDay('a day carrying both an apparatus note and an office note',
      d => (d.notes || []).some(n => /always kept as the Epiphany/.test(n.text || '')));
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('.day-note-details-body p').first())
      .toContainText('always kept as the Epiphany');
    await expect(page.locator('.day-note')).toContainText('Office Note');
  });

  test('pastoral customs still render in the open', async ({ page }) => {
    const date = findDay('a day whose note is a pastoral custom',
      d => (d.notes || []).some(n => n.type === 'pastoral' && /Gaudete/.test(n.text || '')));
    await gotoOffice(page, date, 'mp');
    await expect(page.locator('.day-note')).toContainText('Gaudete');
    await expect(page.locator('.day-note-details')).toHaveCount(0);
  });
});
