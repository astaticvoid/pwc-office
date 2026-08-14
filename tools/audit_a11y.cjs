#!/usr/bin/env node
/**
 * tools/audit_a11y.cjs — static accessibility checks for rendered office HTML.
 *
 * Verifies heading hierarchy, ARIA attributes on interactive elements,
 * basic markup correctness across all forms, and WCAG AA contrast for every
 * palette pair the app actually paints. No browser needed.
 *
 * Usage: node tools/audit_a11y.cjs [--json]
 *
 * The structural checks are advisory (exit 0) and stay that way. The contrast
 * check gates: its inputs are the stylesheet's own tokens, so a failure is a
 * measurement rather than a heuristic, and every known-failing pair is licensed
 * against an open issue in KNOWN_CONTRAST below.
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

/* ── Contrast ──────────────────────────────────────────────────────────────
 *
 * The palette is read out of web/office.css rather than restated here, so the
 * audit cannot quietly disagree with the sheet it is auditing. What *is*
 * declared here is which ground each foreground is painted on, and at what
 * opacity — the cascade knows both and a regex does not.
 *
 * Two scans keep those tables honest, because a table of the pairs someone
 * remembered is worth nothing: every `color:` declaration in the sheet must
 * name a token that appears in TEXT_PAIRS, GRAPHIC_PAIRS or DECORATIVE (or a
 * literal that appears in LITERAL_PAIRS), and every `opacity:` under 1 must
 * name a selector that appears in OPACITY_RULES. An undeclared one fails.
 */

const AA_TEXT = 4.5;      // body-size text; nothing in this palette is large-text only
const AA_GRAPHIC = 3.0;   // non-text glyphs and UI component boundaries

// Grounds the app paints text on. The two color-mix values are the active
// alternatives pill and the active day control.
const MIX_GROUNDS = {
  'brass-10%': { a: '--color-brass', b: '--color-bg', p: 0.10 },
  'brass-15%': { a: '--color-brass', b: '--color-bg', p: 0.15 },
};

const TEXT_PAIRS = [
  { fg: '--color-text',         grounds: ['--color-bg', '--color-surface'], why: 'body text, meta values, settings labels' },
  { fg: '--color-muted',        grounds: ['--color-bg', '--color-surface'], why: 'psalm titles, meta, day notes, scripture attribution, inactive controls' },
  { fg: '--color-heading',      grounds: ['--color-bg', '--color-surface', 'brass-10%', 'brass-15%'], why: 'titles, sheet heads, active pill labels' },
  { fg: '--color-rubric',       grounds: ['--color-bg', '--color-surface'], why: 'rubrics, error text' },
  { fg: '--color-link',         grounds: ['--color-bg', '--color-surface'], why: 'links inside day notes' },
  { fg: '--color-accent',       grounds: ['--color-bg', '--color-surface'], why: 'office name, antiphon label, bio toggle, expand button' },
  { fg: '--color-brass-ink',    grounds: ['--color-bg', '--color-surface'], why: 'verse numbers, psalm midpoint' },
  { fg: '--color-nav-text',     grounds: ['--color-nav-bg'], why: 'nav bar, active segmented control' },
  { fg: '--color-brass-on-nav', grounds: ['--color-nav-bg'], why: 'nav logo and brand' },
  { fg: '--color-bg',           grounds: ['--color-rubric'], why: '.error-retry-btn:hover inverts' },
];

const GRAPHIC_PAIRS = [
  { fg: '--color-brass', grounds: ['--color-bg'], why: '◆ observance marker glyph in the day-control caption' },
];

/**
 * Text painted through `opacity`, which composites against the ground before
 * the eye ever sees the token: `--color-muted` at 0.8 is 3.64:1 on the page,
 * not 5.57:1. The whole point of #85 is that small print was failing unnoticed,
 * so an audit that measured only the raw token would certify exactly the same
 * text green by a different route. Each entry is measured as its own pair.
 *
 * **The alpha is not declared here** — it is read from the sheet, so changing
 * `opacity: 0.78` to `0.12` is measured rather than checked against a
 * remembered number. Declaring it would rebuild the #85 failure mode one layer
 * up. What the table declares is only what the cascade knows and the value
 * cannot say: the ink, the ground, and whether the element carries its own
 * background (`over`), in which case the element's opacity dims that background
 * against the surface behind it too.
 *
 * `:hover` states that restore opacity to 1 need no entry — only values under 1
 * are measured, and a selector listed here that the sheet no longer dims fails.
 */
const OPACITY_RULES = [
  { selector: '#nav a',           fg: '--color-nav-text',     ground: '--color-nav-bg', min: AA_TEXT },
  { selector: '.today-btn:hover', fg: '--color-nav-text',     ground: '--color-nav-bg', over: '--color-surface', min: AA_TEXT },
  // Icons and a logotype, not text: WCAG asks 3:1 of a meaningful graphic, and
  // exempts logotypes entirely. Both are measured at 3:1 rather than exempted.
  { selector: '.nav-icon-btn',    fg: '--color-brass-on-nav', ground: '--color-nav-bg', min: AA_GRAPHIC },
  { selector: '.nav-logo',        fg: '--color-brass-on-nav', ground: '--color-nav-bg', min: AA_GRAPHIC },
];

/** Selectors whose `opacity` paints no content: scrims, and aria-hidden ornament. */
const OPACITY_EXEMPT = {
  '.settings-backdrop': 'the sheet scrim — a translucent ground, not content painted on one',
  '.colour-cycle-hint': 'the "↺" ornament beside the colour chip, aria-hidden and repeating the chip beside it',
};

/**
 * Foregrounds written as literal colours rather than tokens. Licensed per
 * selector, not per value: a colour is only unmeasured where this table says
 * which ground it lands on.
 */
const LITERAL_PAIRS = [
  { selector: '.seg-rubric', fg: '#7A3030', ground: '#FFFFFF', min: AA_TEXT, why: 'print stylesheet — the ground is paper, not a token' },
];

// Painted, but carrying no information: contrast has nothing to protect.
const DECORATIVE = {
  '--color-border': '.meta-sep — the "·" between metadata items, and every border/rule use',
};

/**
 * Divergences that are tracked as open issues, so the audit gates on *new*
 * ones. As with tools/conservation_baseline.json, an entry is a licence to keep
 * failing, not a claim the pair is acceptable: a licensed pair that starts
 * passing fails too, so the entry is deleted by the commit that fixes it.
 * Key: `theme/season/fg/ground`; season is `-` for pairs that do not vary.
 */
const KNOWN_CONTRAST = {
  // #107 — verse numbers and the psalm midpoint asterisk, 4.29 on the page ground.
  'light/-/--color-brass-ink/--color-bg': 107,

  // #106 — the seasonal accent is painted as text (office name, antiphon label,
  // bio toggle, expand button). Five seasons have no dark override at all and
  // keep their light value on the dark ground, which is the worst of it.
  'light/Christmas/--color-accent/--color-bg': 106,
  'light/Christmas/--color-accent/--color-surface': 106,
  'light/Easter/--color-accent/--color-bg': 106,
  'light/Easter/--color-accent/--color-surface': 106,
  'dark/Advent/--color-accent/--color-bg': 106,
  'dark/Advent/--color-accent/--color-surface': 106,
  'dark/Epiphany/--color-accent/--color-bg': 106,
  'dark/Epiphany/--color-accent/--color-surface': 106,
  'dark/Lent/--color-accent/--color-surface': 106,
  'dark/Passiontide/--color-accent/--color-bg': 106,
  'dark/Passiontide/--color-accent/--color-surface': 106,
  'dark/Pentecost/--color-accent/--color-surface': 106,
  'dark/AllSaints/--color-accent/--color-bg': 106,
  'dark/AllSaints/--color-accent/--color-surface': 106,
  'dark/OrdinaryTime/--color-accent/--color-bg': 106,
  'dark/OrdinaryTime/--color-accent/--color-surface': 106,
};

function srgbToLinear(c) { return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }
function linearToSrgb(c) { return c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055; }

function parseHex(hex) {
  const h = hex.replace('#', '');
  return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
}

function toHex(rgb) {
  return '#' + rgb.map(v => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0').toUpperCase()).join('');
}

function relativeLuminance(hex) {
  const [r, g, b] = parseHex(hex).map(srgbToLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(fg, bg) {
  const a = relativeLuminance(fg), b = relativeLuminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

// CSS color-mix(in oklab, A p%, B) — the two tinted grounds in office.css.
function srgbToOklab(hex) {
  const [r, g, b] = parseHex(hex).map(srgbToLinear);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
  ];
}

function oklabToSrgb([L, A, B]) {
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ].map(linearToSrgb);
}

function mixOklab(aHex, bHex, p) {
  const a = srgbToOklab(aHex), b = srgbToOklab(bHex);
  return toHex(oklabToSrgb(a.map((v, i) => v * p + b[i] * (1 - p))));
}

/** Text at `alpha` over `ground` — plain sRGB compositing, as the browser does. */
function composite(fg, ground, alpha) {
  const f = parseHex(fg), g = parseHex(ground);
  return toHex(f.map((v, i) => v * alpha + g[i] * (1 - alpha)));
}

/**
 * Walk every style rule in the sheet, innermost first, skipping the at-rule
 * wrappers themselves so a rule inside `@media print` is still visited. Comments
 * are stripped first: the sheet's own prose quotes colours and selectors.
 */
function eachRule(css, fn) {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const stack = [];
  let buf = '';
  for (const ch of clean) {
    if (ch === '{') { stack.push(buf.trim()); buf = ''; }
    else if (ch === '}') {
      const selector = stack.pop();
      if (selector && !selector.startsWith('@')) fn(selector, buf, stack.filter(s => s.startsWith('@')));
      buf = '';
    } else buf += ch;
  }
}

/**
 * Read the palette out of web/office.css: the base tokens, the dark-theme
 * overrides, and every per-season override in both themes. Returns
 * `{ [theme]: { [season]: {token: hex} } }`.
 *
 * Whole declaration blocks are merged rather than the accent picked out of
 * them, so a seasonal rule that sets some other token is carried instead of
 * silently blanking the season.
 */
function readPalette(css) {
  const base = {}, darkBase = {};
  const seasonal = { light: {}, dark: {} };

  eachRule(css, (selector, body, atRules) => {
    const decls = Object.fromEntries(
      [...body.matchAll(/(--color-[a-z-]+):\s*(#[0-9A-Fa-f]{6})\s*;/g)].map(m => [m[1], m[2]]));
    if (!Object.keys(decls).length) return;
    if (atRules.length) {
      // One palette per theme is the whole model here. A token that depends on
      // a media or feature query is a second palette the audit cannot see.
      throw new Error(`readPalette: ${Object.keys(decls).join(', ')} declared inside ${atRules.join(' / ')} — teach audit_a11y.cjs about that context before shipping it`);
    }
    const season = /\[data-season="(\w+)"\]/.exec(selector);
    const theme = selector.includes('[data-theme="dark"]') ? 'dark' : 'light';
    if (season) {
      Object.assign(seasonal[theme][season[1]] ||= {}, decls);
    } else if (theme === 'dark') {
      Object.assign(darkBase, decls);
    } else if (selector.includes(':root') || selector.includes('[data-theme="light"]')) {
      Object.assign(base, decls);
    } else {
      throw new Error(`readPalette: ${selector} declares ${Object.keys(decls).join(', ')} in a context the audit does not model — teach it about that selector before shipping it`);
    }
  });

  if (!Object.keys(base).length) throw new Error('readPalette: no :root colour tokens found in office.css');

  const palette = {};
  const seasons = new Set([...Object.keys(seasonal.light), ...Object.keys(seasonal.dark)]);
  for (const theme of ['light', 'dark']) {
    palette[theme] = {};
    for (const season of seasons) {
      /*
       * Cascade order, not convenience order. `[data-season="X"]` and
       * `[data-theme="dark"]` have equal specificity (0,1,0) and the dark block
       * is written after the seasonal ones, so the dark base wins between them;
       * only `[data-theme="dark"][data-season="X"]` (0,2,0) beats it. A season
       * with neither keeps its light value, which is how five ended up
       * unreadable in dark mode (#106).
       */
      palette[theme][season] = theme === 'dark'
        ? { ...base, ...(seasonal.light[season] || {}), ...darkBase, ...(seasonal.dark[season] || {}) }
        : { ...base, ...(seasonal.light[season] || {}) };
    }
  }
  return palette;
}

/**
 * Every selector in the sheet that dims its content, and the alphas it uses.
 * The last `opacity` in a block wins, as the cascade does; a selector written
 * twice (a base rule and a media override) contributes each distinct value,
 * since which one applies depends on a query this audit does not evaluate.
 */
function readOpacities(css) {
  const dimmed = new Map();
  eachRule(css, (selector, body) => {
    const values = [...body.matchAll(/(?:^|;)\s*opacity:\s*([\d.]+)/g)];
    if (!values.length) return;
    const alpha = parseFloat(values[values.length - 1][1]);
    if (alpha < 1) (dimmed.get(selector) || dimmed.set(selector, new Set()).get(selector)).add(alpha);
  });
  return dimmed;
}

/** A token named in the tables above but absent from the sheet is an error, not a crash. */
function lookup(tokens, token, where) {
  const hex = token.startsWith('#') ? token : tokens[token];
  if (!hex) throw new Error(`${where}: ${token} is not defined in web/office.css — was it renamed, or written as something other than #RRGGBB?`);
  return hex;
}

function auditContrast(css) {
  const palette = readPalette(css);
  const failures = [], stale = [];
  const checked = new Set();
  const visited = new Set();

  const resolve = (tokens, ground) => {
    const mix = MIX_GROUNDS[ground];
    return mix
      ? mixOklab(lookup(tokens, mix.a, 'MIX_GROUNDS'), lookup(tokens, mix.b, 'MIX_GROUNDS'), mix.p)
      : lookup(tokens, ground, 'ground');
  };

  const measure = (key, ratio, min, why) => {
    visited.add(key);
    const passes = ratio >= min;
    if (!passes && !(key in KNOWN_CONTRAST)) {
      failures.push({ key, ratio: +ratio.toFixed(2), min, why });
    } else if (passes && key in KNOWN_CONTRAST) {
      stale.push({ key, ratio: +ratio.toFixed(2), issue: KNOWN_CONTRAST[key], why: 'passes now — delete the licence' });
    }
  };

  /*
   * Which pairs vary by season is read off the palette rather than declared:
   * a pair resolving to the same two colours in all nine seasons is measured
   * once under season `-`, and any pair that differs — the accent today, any
   * token a future seasonal rule overrides — is measured per season. Declaring
   * it instead would mean a seasonal override of a token nobody had marked
   * seasonal went measured in one season and unmeasured in eight.
   */
  const dimmed = readOpacities(css);
  const pairs = [
    ...TEXT_PAIRS.map(p => ({ ...p, min: AA_TEXT })),
    ...GRAPHIC_PAIRS.map(p => ({ ...p, min: AA_GRAPHIC })),
  ];

  // Every alpha the sheet actually uses for a declared selector, rather than a
  // remembered one. A declared selector the sheet no longer dims is a stale
  // table entry and says so.
  for (const rule of OPACITY_RULES) {
    const alphas = dimmed.get(rule.selector);
    if (!alphas) {
      failures.push({ key: `-/-/${rule.selector}/?`, ratio: null, min: null,
        why: 'declared in OPACITY_RULES but the sheet no longer dims it — delete the entry' });
      continue;
    }
    for (const alpha of alphas) {
      pairs.push({ ...rule, alpha, grounds: [rule.ground], label: `${rule.selector}@${alpha}`,
        why: `${rule.fg} at opacity ${alpha}${rule.over ? ` over ${rule.over}` : ''}` });
    }
  }

  for (const [theme, seasons] of Object.entries(palette)) {
    for (const pair of pairs) {
      const { fg, grounds, why, min, alpha, over, label } = pair;
      checked.add(fg);
      for (const ground of grounds) {
        const resolved = Object.entries(seasons).map(([season, tokens]) => {
          const g = resolve(tokens, ground);
          const ink = lookup(tokens, fg, label || 'palette pair');
          if (!alpha) return { season, ink, ground: g };
          // An element with its own background dims that too, so both sides
          // composite against whatever it sits on; a transparent one dims only
          // its ink, against the ground showing through.
          const outer = over ? resolve(tokens, over) : null;
          return outer
            ? { season, ink: composite(ink, outer, alpha), ground: composite(g, outer, alpha) }
            : { season, ink: composite(ink, g, alpha), ground: g };
        });
        const uniform = resolved.every(r => r.ink === resolved[0].ink && r.ground === resolved[0].ground);
        for (const r of (uniform ? [{ ...resolved[0], season: '-' }] : resolved)) {
          measure(`${theme}/${r.season}/${label || fg}/${ground}`, contrastRatio(r.ink, r.ground), min, why);
        }
      }
    }
  }

  for (const { selector, fg, ground, min, why } of LITERAL_PAIRS) {
    measure(`-/-/${selector}/${ground}`, contrastRatio(fg, ground), min, why);
  }

  for (const selector of Object.keys(OPACITY_EXEMPT)) {
    if (!dimmed.has(selector)) {
      stale.push({ key: `-/-/${selector}/?`, ratio: null, issue: 'OPACITY_EXEMPT',
        why: 'exempted from the opacity scan but the sheet no longer dims it — delete the entry' });
    }
  }

  // The two scans. Without them the tables above are a list of the pairs
  // someone remembered rather than the pairs the sheet actually paints.
  eachRule(css, (selector, body) => {
    for (const [, value] of body.matchAll(/(?:^|;)\s*color:\s*([^;]+)/g)) {
      const tokens = [...value.matchAll(/(--color-[a-z-]+)/g)].map(m => m[1]);
      if (!tokens.length) {
        // `inherit`/`currentColor` take their contrast from the rule that set it.
        if (/^\s*(inherit|currentColor|unset|initial)\s*$/i.test(value)) continue;
        // Keyed on the selector, not the colour: licensing #7A3030 for the
        // print rubric must not licence it everywhere, on any ground.
        if (!LITERAL_PAIRS.some(p => p.selector === selector && value.includes(p.fg))) {
          failures.push({ key: `-/-/${selector}/?`, ratio: null, min: null,
            why: `paints a literal foreground (${value.trim()}) with no entry in LITERAL_PAIRS` });
        }
        continue;
      }
      for (const fg of tokens) {
        if (!checked.has(fg) && !(fg in DECORATIVE)) {
          failures.push({ key: `-/-/${fg}/?`, ratio: null, min: null,
            why: `painted as a foreground by ${selector} but has no declared ground` });
        }
      }
    }
  });

  // readOpacities applies the cascade within a block, so a rule that resets
  // opacity to 1 further down is not read as dimming.
  for (const [selector, alphas] of dimmed) {
    if (OPACITY_RULES.some(r => r.selector === selector) || selector in OPACITY_EXEMPT) continue;
    for (const alpha of alphas) {
      failures.push({ key: `-/-/${selector}@${alpha}/?`, ratio: null, min: null,
        why: 'dims its content with opacity but has no entry in OPACITY_RULES' });
    }
  }

  // A licence for a pair nothing measures any more is as stale as one that
  // passes: the pair may have been renamed, or dropped from the tables.
  for (const key of Object.keys(KNOWN_CONTRAST)) {
    if (!visited.has(key)) {
      stale.push({ key, ratio: null, issue: KNOWN_CONTRAST[key], why: 'licensed but no longer measured — the pair is gone from the tables' });
    }
  }
  return { failures, stale };
}

async function main() {
  const {
    assembleSections, renderSegments, rubricBlockSegments,
    invitatorySegments, phosHilaronSegments,
  } = await import('../web/render.js');
  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared = offices._shared || {};
  const useJson = process.argv.includes('--json');

  const failures = [];
  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));

  // Which _shared blocks the form pass actually renders. A block nothing looks
  // at is as much a hole as one that fails — it is how #109 stayed quiet, the
  // audit reporting "all forms pass" while four of the six were out of reach.
  // walkSegments resolves a ref and drops the key, so track them here.
  const reachedShared = new Set();
  const noteShared = (segs) => {
    if (!segs) return;
    for (const seg of Array.isArray(segs) ? segs : [segs]) {
      // Already-seen doubles as the cycle guard: renderSegments resolves a ref
      // once and stops, so a self-referential block would hang only here.
      if (seg.type === 'shared') {
        if (reachedShared.has(seg.key)) continue;
        reachedShared.add(seg.key);
        noteShared(shared[seg.key]);
      }
      else if (seg.type === 'alternatives') for (const g of seg.groups || []) noteShared(g.segments);
    }
  };

  // Render a minimal office to check HTML structure
  for (const fk of formKeys) {
    const form = offices[fk];

    // Every segment-bearing field on the form. The list used to hold six, and
    // omitting the rest was not a judgement about which ones matter: the tabs
    // this audit checks come from `alternatives` segments, which extraction may
    // put in any of them (#109). title/subtitle are strings, not segments, and
    // are the only fields deliberately absent.
    //
    // `prepare` is how a field has to be handed to renderSegments to match what
    // the app renders — the label the block carries for its own heading is the
    // subsection title both renderers already emit, so it is stripped first.
    const renderables = [
      { field: 'opening_responses', label: 'Opening Responses', verse: false },
      { field: 'thanksgiving_for_light', label: 'Thanksgiving for Light', verse: false },
      { field: 'phos_hilaron', label: 'Evening Hymn', verse: true, prepare: s => phosHilaronSegments({ phos_hilaron: s }) },
      { field: 'invitatory', label: 'Invitatory Psalm', verse: true, prepare: s => invitatorySegments({ invitatory: s }) },
      { field: 'psalm_rubrics', label: 'Psalm Rubrics', verse: false, prepare: rubricBlockSegments },
      { field: 'reading_rubrics', label: 'Reading Rubrics', verse: false, prepare: rubricBlockSegments },
      { field: 'reading_response', label: 'Reading Response', verse: false },
      { field: 'responsory', label: 'Responsory', verse: true },
      { field: 'canticle', label: 'Canticle', verse: true },
      { field: 'affirmation', label: 'Affirmation', verse: false },
      { field: 'intercessions', label: 'Intercessions', verse: false },
      { field: 'litany', label: 'Litany', verse: false },
      { field: 'seasonal_collects', label: 'Seasonal Collects', verse: false },
      { field: 'lords_prayer_intro', label: "Lord's Prayer Intro", verse: false },
      { field: 'dismissal', label: 'Dismissal', verse: true },
    ];

    for (const { field, label, verse, prepare } of renderables) {
      if (!form[field]) continue;
      // A field normalize_offices.py hoisted into _shared is a {type,key} ref,
      // not an array. Skipping those on shape — which is what this loop did —
      // dropped the whole field from the audit silently, and drops any field
      // hoisted next. Resolve the ref instead; a dangling one is itself a
      // finding, since nothing would render on the page either.
      let segs = form[field];
      if (!Array.isArray(segs)) {
        if (segs.type !== 'shared') continue;
        const resolved = shared[segs.key];
        if (!resolved) {
          failures.push({ form: fk, section: label, detail: `shared ref "${segs.key}" resolves to nothing` });
          continue;
        }
        segs = Array.isArray(resolved) ? resolved : [resolved];
      }
      noteShared(form[field]);
      const html = renderSegments(prepare ? prepare(segs) : segs, shared, verse);

      // 1. Check for missing ARIA attributes on interactive elements
      // Alternatives tabs are the main interactive elements
      const tabs = html.match(/<button[^>]*>/g) || [];
      for (const tab of tabs) {
        if (!/role="tab"/.test(tab)) {
          failures.push({ form: fk, section: label, detail: 'button missing role="tab"' });
        }
        if (!/aria-selected/.test(tab)) {
          failures.push({ form: fk, section: label, detail: 'button missing aria-selected' });
        }
        if (!/aria-controls/.test(tab)) {
          failures.push({ form: fk, section: label, detail: 'button missing aria-controls' });
        }
      }

      const panels = html.match(/<div[^>]*role="tabpanel"[^>]*>/g) || [];
      for (const panel of panels) {
        if (!/aria-labelledby/.test(panel)) {
          failures.push({ form: fk, section: label, detail: 'tabpanel missing aria-labelledby' });
        }
      }
    }

    // 3. No empty alt attributes on meaningful content
  }

  // 3b. Coverage: every shared block has to have been rendered by something
  // above, or the pass is reporting on a corpus it did not read.
  for (const key of Object.keys(shared)) {
    if (!reachedShared.has(key)) {
      failures.push({ form: '_shared', section: key,
        detail: 'shared block unaudited — no field in renderables reaches it' });
    }
  }

  // 4. Check heading hierarchy in a full rendered form
  // Use ordinary-sunday-mp as representative
  const fk = 'ordinary-sunday-mp';
  const form = offices[fk];
  if (form) {
    const cfg = {
      form, shared,
      officeData: { psalms: [{ citation: '145' }], lessons: [{ citation: 'Isaiah 55:1-5' }] },
      officeType: 'mp', season: 'OrdinaryTime', weekIdx: 0,
    };
    const asm = assembleSections(cfg);

    // Verify h2/h3 count matches section structure
    const expectedH2 = asm.sections.filter(s => s.visible && s.name !== 'Unknown').length;

    // Build the HTML to verify
    let html = '';
    for (const section of asm.sections) {
      const sectionLabels = {
        Gathering: 'The Gathering of the Community',
        Proclamation: 'The Proclamation of the Word',
        Affirmation: 'The Affirmation of Faith',
        Prayers: 'The Prayers of the Community',
        Sending: 'The Sending Forth of the Community',
      };
      const label = sectionLabels[section.name];
      if (!label) continue;
      html += `<h2 class="office-section-title">${label}</h2>`;
      for (const sub of section.subsections) {
        html += `<h3 class="office-subsection-title">${sub.label}</h3>`;
      }
    }

    const h2Count = (html.match(/<h2\b/g) || []).length;
    if (h2Count !== expectedH2) {
      failures.push({ form: fk, section: 'structure', detail: `h2 count ${h2Count} vs expected ${expectedH2}` });
    }
  }

  const contrast = auditContrast(readFileSync(join(root, 'web/office.css'), 'utf8'));

  if (useJson) {
    console.log(JSON.stringify({
      forms_checked: formKeys.length,
      failures: failures,
      failure_count: failures.length,
      contrast_failures: contrast.failures,
      contrast_stale_licences: contrast.stale,
      contrast_licensed: Object.keys(KNOWN_CONTRAST).length,
    }, null, 2));
    process.exit(contrast.failures.length || contrast.stale.length ? 1 : 0);
  }

  console.log(`Accessibility audit: ${formKeys.length} forms`);
  if (failures.length === 0) {
    console.log('All forms pass structural accessibility checks.');
  } else {
    // Advisory — these do not gate.
    console.log(`\n${failures.length} structural failure(s):\n`);
    for (const f of failures) {
      console.log(`  ${f.form} ${f.section}: ${f.detail}`);
    }
  }

  const licensed = Object.keys(KNOWN_CONTRAST).length;
  console.log(`\nContrast: WCAG AA over the office.css palette${licensed ? `, ${licensed} pair(s) licensed against open issues` : ''}`);
  for (const f of contrast.failures) {
    console.log(f.ratio === null
      ? `  ${f.key.split('/').slice(2).join('/')}: ${f.why}`
      : `  ${f.key}: ${f.ratio.toFixed(2)}:1, needs ${f.min.toFixed(1)}:1 — ${f.why}`);
  }
  for (const s of contrast.stale) {
    console.log(`  ${s.key}: ${s.ratio === null ? s.why : `now ${s.ratio.toFixed(2)}:1 — ${s.why}`} (issue ${s.issue})`);
  }
  if (!contrast.failures.length && !contrast.stale.length) {
    console.log('  All declared pairs clear AA.');
    return;
  }
  process.exit(1);
}

if (require.main === module) {
  main().catch(e => { console.error(e); process.exit(1); });
}

module.exports = { contrastRatio, mixOklab, composite, readPalette, auditContrast, KNOWN_CONTRAST };
