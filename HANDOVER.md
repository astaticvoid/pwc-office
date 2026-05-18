# Handover — Extraction Fixes & Rendering

_Last updated: 2026-05-17_

## What was just done

Added `DEBUG=1` tracing to `tools/extract_offices.py`. Full audit of all 30
offices revealed these silent data-loss bugs:

| Unknown heading | Offices | Wrong section | Fix |
|---|---|---|---|
| `thanksgiving` | 8 seasonal EP | bleeds into `opening_responses` | → `thanksgiving_for_light` |
| `intercessions and thanksgivings` | 14 ordinary-time | `None` (dropped!) | → `intercessions` |
| `the evening hymn: "..."` | 7 ordinary-time EP | `opening_responses` | → `phos_hilaron` |
| `the Lord's Prayer` | all 30 | `litany` (harmless) | fix curly apostrophe regex |

## Extraction fixes needed (`tools/extract_offices.py`)

All changes are in `_SUB_HDR_MAP` and the section-order list at the bottom
of `extract_office()`.

### 1. Add missing headings to `_SUB_HDR_MAP`

```python
_SUB_HDR_MAP: list[tuple[re.Pattern, str | None]] = [
    (re.compile(r'introductory Responses',          re.IGNORECASE), "opening_responses"),
    (re.compile(r'invitatory Psalm',                re.IGNORECASE), "invitatory"),
    (re.compile(r'^thanksgiving$',                  re.IGNORECASE), "thanksgiving_for_light"),  # ADD
    (re.compile(r'^intercessions and thanksgivings$', re.IGNORECASE), "intercessions"),          # ADD
    (re.compile(r'^the evening hymn\b',             re.IGNORECASE), "phos_hilaron"),             # ADD
    (re.compile(r'^the Responsory$',                re.IGNORECASE), "responsory"),
    (re.compile(r'^the Canticle$',                  re.IGNORECASE), "canticle"),
    (re.compile(r'Affirmation of faith',            re.IGNORECASE), "affirmation"),
    (re.compile(r'^the Litany$',                    re.IGNORECASE), "litany"),
    (re.compile(r"the Lord[’']?s Prayer",      re.IGNORECASE), "lords_prayer"),  # fix curly apostrophe
    (re.compile(r'^the dismissal$',                 re.IGNORECASE), "dismissal"),
    (re.compile(r'^the Reading$',                   re.IGNORECASE), None),
    (re.compile(r'^the Psalm$',                     re.IGNORECASE), None),
]
```

### 2. Add new keys to section-order list in `extract_office()`

```python
for key in ("opening_responses", "thanksgiving_for_light", "phos_hilaron",
            "invitatory", "responsory", "canticle",
            "affirmation", "litany", "intercessions", "seasonal_collects",
            "lords_prayer_intro", "dismissal"):
```

Note: `phos_hilaron` will contain just a heading/rubric in ordinary-time EP
(the hymn title). `thanksgiving_for_light` will contain the full thanksgiving
prayer + alternatives. `intercessions` will contain the rubric + day-specific
prayer topic prompts.

### 3. Christmas-MP unknown heading

`christmas-mp` has `UNKNOWN-HDR → content in 'opening_responses':
'Let heaven and earth shout their praise.'` — this appears to be a seasonal
acclamation heading. Investigate what follows it in the PDF (book p. 29–35).
May need its own key or can be discarded.

### 4. AllSaints-MP repeated heading ×4

`allsaints-mp` has `UNKNOWN-HDR → content in 'litany':
'God of all the faithful, we thank you.'` appearing 4 times. This is almost
certainly a mis-classified bold line (a leader/response that the font
classifier read as `heading`). Check the PDF around pages 114–120.
May need a threshold adjustment in `_char_type()` or a specific suppression.

## After re-extraction, re-run spot checks

```
python3 tools/extract_offices.py
```

Expected: all seasonal EP `opening_responses` should now have 2 groups (I, II).
Ordinary-time offices should have a new `intercessions` section.

## Web app rendering (`web/app.js`)

After extraction is fixed, three new sections need rendering:

### `thanksgiving_for_light` (seasonal EP Gathering)

Add rendering between introductory responses and proclamation in `render()`.
It is **optional** — show with a leading rubric: "The Service of Light may
begin Evening Prayer." The content is already properly structured alternatives
(the three blessing conclusions are already a nested alt-block from the
extraction). Render as `renderSubsection('The Thanksgiving for Light', ...)`.

```js
// In Gathering section of render():
if (form && form.thanksgiving_for_light && form.thanksgiving_for_light.length) {
  html += `<p class="seg-rubric">The Service of Light may begin Evening Prayer.</p>`;
  html += renderSubsection('The Thanksgiving for Light', form.thanksgiving_for_light, shared);
}
```

### `phos_hilaron` (ordinary-time EP Gathering)

The heading text IS the hymn title (e.g., "the evening hymn: 'o Gracious
Light, Lord Jesus Christ'"). Render as a rubric placeholder:

```js
if (form && form.phos_hilaron && form.phos_hilaron.length) {
  // First segment will be the rubric with the hymn title
  html += `<div class="liturgy">${renderSegments(form.phos_hilaron, shared)}</div>`;
}
```

Future: include full Phos Hilaron text (public domain, 3rd century). Several
good translations exist. Could be a shared block in `_shared`.

### `intercessions` (ordinary-time Prayers)

Render BEFORE the Litany in the Prayers section. These are the day-specific
prayer topic prompts that guide the free-prayer period. They are rubrics —
possibly formatted as a bullet list (• media and arts • farming...).

```js
// In Prayers section of render():
if (form && form.intercessions && form.intercessions.length) {
  html += renderSubsection('Intercessions and Thanksgivings', form.intercessions, shared);
}
```

Future affordance: this is the right place for a user's personal prayer
intentions. The structure already exists — the app just needs a way to persist
and display user-added intentions alongside the liturgical prompts.

## EP structural order (correct, per BAS pp. 60–65)

When Service of Light is used (seasonal EP):
1. Introductory Responses (2 options)
2. Phos Hilaron — sung while candles are lit (not in PWC text, reference only)
3. Thanksgiving for Light — seasonal prayer + blessing conclusion choice
4. [Psalm 141 — optional, not extracted]
5. Proclamation of the Word

When Service of Light is not used (ordinary-time EP):
1. Introductory Responses (3 options)
2. Evening Hymn (Phos Hilaron reference per weekday)
3. Proclamation of the Word

Note: Phos Hilaron comes BEFORE the thanksgiving in the seasonal form, not
after. Current extraction has this correct structurally (they're separate
sections) but the renderer will need to emit them in the right order.

## E2E tests to add after fixes

- Seasonal EP opening_responses has exactly 2 tabs (not 5)
- Seasonal EP renders Thanksgiving for Light subsection
- Ordinary-time EP renders evening hymn rubric
- Ordinary-time MP/EP renders intercessions prompts before litany

## PLAN.md items to close

- "Missing transitional rubrics" — partially addressed by `thanksgiving_for_light`
  and `intercessions`; full rubric restoration still needs PDF re-examination
  for "Morning/Evening Prayer continues with…" connectives

## Known remaining gaps (not blocking)

- Phos Hilaron full text not included (public domain, could add)
- Psalm 141 (optional in Service of Light) not extracted
- Christmas-MP acclamation heading unresolved
- AllSaints-MP repeated heading unresolved
- Collect 668 (Occasional Prayers, Oct dates) still shows page ref only
