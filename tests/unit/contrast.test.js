/**
 * The contrast half of tools/audit_a11y.cjs (issue #85).
 *
 * The audit is only worth its exit code if it fails on a palette that should
 * fail, so most of this file mutates the real stylesheet and asserts the audit
 * notices — including the exact regression it was written for.
 */
import { describe, test, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const { contrastRatio, mixOklab, composite, readPalette, auditContrast, KNOWN_CONTRAST } =
  require('../../tools/audit_a11y.cjs');

const CSS_PATH = join(import.meta.dirname, '../../web/office.css');
const css = readFileSync(CSS_PATH, 'utf8');

const keysOf = list => list.map(f => f.key);

// KNOWN_CONTRAST is empty now that every real pair clears AA (#106), so the
// stale-licence tests below inject a temporary entry to exercise the
// detection logic and remove it immediately after — never left for another
// test in this file to see.
function withLicence(key, issue, fn) {
  KNOWN_CONTRAST[key] = issue;
  try {
    return fn();
  } finally {
    delete KNOWN_CONTRAST[key];
  }
}

describe('contrast maths', () => {
  test('the WCAG extremes', () => {
    expect(contrastRatio('#000000', '#FFFFFF')).toBeCloseTo(21, 5);
    expect(contrastRatio('#7B7460', '#7B7460')).toBeCloseTo(1, 5);
  });

  test('is symmetric — a pair does not depend on which side is the ink', () => {
    expect(contrastRatio('#655E4B', '#F4EEDF')).toBeCloseTo(contrastRatio('#F4EEDF', '#655E4B'), 10);
  });

  test('the two ratios issue #85 turns on', () => {
    // The old token, against both light grounds: what failed.
    expect(contrastRatio('#7B7460', '#F4EEDF')).toBeCloseTo(4.02, 2);
    expect(contrastRatio('#7B7460', '#FBF6EB')).toBeCloseTo(4.32, 2);
    // The replacement.
    expect(contrastRatio('#655E4B', '#F4EEDF')).toBeCloseTo(5.57, 2);
    expect(contrastRatio('#655E4B', '#FBF6EB')).toBeCloseTo(5.98, 2);
  });
});

describe('oklab mixing', () => {
  test('the endpoints are the endpoints', () => {
    expect(mixOklab('#9A7B3F', '#F4EEDF', 1)).toBe('#9A7B3F');
    expect(mixOklab('#9A7B3F', '#F4EEDF', 0)).toBe('#F4EEDF');
  });

  test('a 10% brass tint stays nearer the ground than the tint', () => {
    const mixed = mixOklab('#9A7B3F', '#F4EEDF', 0.10);
    expect(contrastRatio(mixed, '#F4EEDF')).toBeLessThan(1.2);
    expect(contrastRatio(mixed, '#9A7B3F')).toBeGreaterThan(2.5);
  });
});

describe('opacity compositing', () => {
  test('the endpoints are the endpoints', () => {
    expect(composite('#655E4B', '#F4EEDF', 1)).toBe('#655E4B');
    expect(composite('#655E4B', '#F4EEDF', 0)).toBe('#F4EEDF');
  });

  test('dimming a passing token can drop it under AA — the whole reason it is measured', () => {
    expect(contrastRatio('#655E4B', '#F4EEDF')).toBeGreaterThan(4.5);
    expect(contrastRatio(composite('#655E4B', '#F4EEDF', 0.8), '#F4EEDF')).toBeCloseTo(3.64, 2);
  });
});

describe('palette parsing', () => {
  const palette = readPalette(css);

  test('reads both themes and all nine seasons', () => {
    expect(Object.keys(palette)).toEqual(['light', 'dark']);
    expect(Object.keys(palette.light)).toHaveLength(9);
  });

  test('the dark theme overrides the base tokens', () => {
    expect(palette.light.OrdinaryTime['--color-bg']).toBe('#F4EEDF');
    expect(palette.dark.OrdinaryTime['--color-bg']).toBe('#15140E');
  });

  test('a season with no dark accent keeps its light one, as the cascade does', () => {
    expect(palette.dark.Advent['--color-accent']).toBe('#887DC2'); // overridden
    const p = readPalette(css + '\n[data-season="Ascension"] { --color-accent: #101010; }\n');
    expect(p.dark.Ascension['--color-accent']).toBe('#101010'); // no dark rule: the light value carries
  });

  test('a seasonal rule setting some other token keeps both it and the accent', () => {
    const p = readPalette(css + '\n[data-season="Lent"] { --color-heading: #B0863A; }\n');
    expect(p.light.Lent['--color-heading']).toBe('#B0863A');
    expect(p.light.Lent['--color-accent']).toBe('#6B4C8A');
  });

  test('a season defined only in dark mode is still measured', () => {
    const p = readPalette(css + '\n[data-theme="dark"][data-season="Ascension"] { --color-accent: #101010; }\n');
    expect(p.dark.Ascension['--color-accent']).toBe('#101010');
    expect(p.light.Ascension['--color-accent']).toBe('#3B6B4E'); // no light rule: the base
    const { failures } = auditContrast(css + '\n[data-theme="dark"][data-season="Ascension"] { --color-accent: #101010; }\n');
    expect(keysOf(failures)).toContain('dark/Ascension/--color-accent/--color-bg');
  });

  test('the dark base beats a light seasonal rule, as document order does', () => {
    // [data-season] and [data-theme="dark"] are both (0,1,0); the dark block is
    // written later, so it wins. Only [data-theme][data-season] (0,2,0) beats it.
    const p = readPalette(css + '\n[data-season="Advent"] { --color-heading: #4B3F8C; }\n');
    expect(p.light.Advent['--color-heading']).toBe('#4B3F8C');
    expect(p.dark.Advent['--color-heading']).toBe('#86C0A4');
  });

  test('an explicit light-theme block is an override, not a dropped rule', () => {
    const p = readPalette(css + '\n[data-theme="light"] { --color-muted: #000000; }\n');
    expect(p.light.Lent['--color-muted']).toBe('#000000');
  });

  test('colour tokens in a context the audit does not model are refused', () => {
    expect(() => readPalette(css + '\n.rogue { --color-muted: #000000; }\n'))
      .toThrow(/context the audit does not model/);
  });

  test('a token declared inside an at-rule is a second palette, and says so', () => {
    expect(() => readPalette(css + '\n@media print { :root { --color-text: #000000; } }\n'))
      .toThrow(/inside @media print/);
  });

  test('a token the tables name but the sheet does not define is named, not a TypeError', () => {
    expect(() => auditContrast(css.replace(/--color-brass-on-nav/g, '--color-brass-nav')))
      .toThrow(/--color-brass-on-nav is not defined/);
  });
});

describe('the audit over the shipped stylesheet', () => {
  test('every declared pair clears AA, or is licensed', () => {
    const { failures, stale } = auditContrast(css);
    expect(failures).toEqual([]);
    expect(stale).toEqual([]);
  });

  test('every licence names an open issue', () => {
    // Vacuously true while KNOWN_CONTRAST is empty (#106 cleared the last
    // ones) — starts checking again the moment a new licence is added.
    for (const [key, issue] of Object.entries(KNOWN_CONTRAST)) {
      expect(key.split('/')).toHaveLength(4);
      expect(Number.isInteger(issue)).toBe(true);
    }
  });
});

describe('the audit fails when it should', () => {
  test('restoring the old --color-muted fails both light grounds', () => {
    const { failures } = auditContrast(css.replace('--color-muted:       #655E4B', '--color-muted:       #7B7460'));
    expect(keysOf(failures)).toEqual([
      'light/-/--color-muted/--color-bg',
      'light/-/--color-muted/--color-surface',
    ]);
    expect(failures[0].ratio).toBeCloseTo(4.02, 2);
  });

  test('a dark-mode token regression is caught too', () => {
    const { failures } = auditContrast(css.replace('--color-muted:    #9A9281', '--color-muted:    #4A463C'));
    expect(keysOf(failures)).toContain('dark/-/--color-muted/--color-bg');
  });

  test('a licensed pair that starts passing is reported as a stale licence', () => {
    const key = 'dark/Advent/--color-accent/--color-bg';
    withLicence(key, 999, () => {
      const { stale } = auditContrast(css);
      expect(keysOf(stale)).toContain(key);
      expect(stale.find(f => f.key === key).issue).toBe(999);
    });
  });

  test('a newly painted token with no declared ground fails', () => {
    const { failures } = auditContrast(css + '\n.invented { color: var(--color-nav-bg); }\n');
    expect(keysOf(failures)).toEqual(['-/-/--color-nav-bg/?']);
  });

  test('…in every form a foreground can take', () => {
    for (const decl of [
      'color: var(--color-nav-bg, #fff)',                          // fallback syntax
      'color: color-mix(in oklab, var(--color-nav-bg) 50%, white)', // computed
      'color:var(--color-nav-bg)',                                  // no space
    ]) {
      const { failures } = auditContrast(`${css}\n.invented { ${decl}; }\n`);
      expect(keysOf(failures), decl).toEqual(['-/-/--color-nav-bg/?']);
    }
  });

  test('a literal foreground with no LITERAL_PAIRS entry fails', () => {
    const { failures } = auditContrast(css + '\n.invented { color: #999999; }\n');
    expect(keysOf(failures)).toEqual(['-/-/.invented/?']);
  });

  test('the print stylesheet\'s literal rubric is declared, so it does not', () => {
    expect(css).toContain('.seg-rubric { color: #7A3030; }');
    expect(auditContrast(css).failures).toEqual([]);
  });

  test('a new rule dimming its text with opacity fails until it is declared', () => {
    const { failures } = auditContrast(css + '\n.invented { opacity: 0.5; color: var(--color-text); }\n');
    expect(keysOf(failures)).toEqual(['-/-/.invented@0.5/?']);
  });

  test('restoring the day-meta dim via opacity fails — 0.8 on muted is 3.64:1 (issue #85)', () => {
    const { failures } = auditContrast(css.replace('.meta-item { display: flex; align-items: center; gap: 0.35rem; color: var(--color-muted); white-space: nowrap; }', '.meta-item { opacity: 0.8; }'));
    expect(keysOf(failures)).toEqual(['-/-/.meta-item@0.8/?']);
  });

  test('a declared opacity rule is measured, not merely allowed', () => {
    // #nav a is declared at 0.78; drop the nav ground to something it cannot clear.
    const { failures } = auditContrast(css.replace('--color-nav-bg:   #0F1A14;', '--color-nav-bg:   #C9C2B0;'));
    expect(keysOf(failures)).toContain('dark/-/#nav a@0.78/--color-nav-bg');
  });

  test('the alpha comes from the sheet, so dimming further is caught', () => {
    // The #85 failure mode one layer up: an alpha remembered in the table
    // rather than read would keep measuring 0.78 and report green.
    const { failures } = auditContrast(css.replace('opacity: 0.78', 'opacity: 0.12'));
    expect(keysOf(failures)).toEqual([
      'light/-/#nav a@0.12/--color-nav-bg',
      'dark/-/#nav a@0.12/--color-nav-bg',
    ]);
  });

  test('the last opacity in a block wins, in both directions', () => {
    const dimmedLast = auditContrast(css + '\n.invented { opacity: 1; color: var(--color-text); opacity: 0.3; }\n');
    expect(keysOf(dimmedLast.failures)).toEqual(['-/-/.invented@0.3/?']);
    const resetLast = auditContrast(css + '\n.invented { opacity: 0.3; color: var(--color-text); opacity: 1; }\n');
    expect(resetLast.failures).toEqual([]);
  });

  test('an element with its own background dims that too', () => {
    // .today-btn:hover — nav ink on a nav-bg button, both composited over the
    // sheet's surface. Measuring the ink alone would overstate this by ~19%.
    const composited = contrastRatio(composite('#F3EEDF', '#FBF6EB', 0.85), composite('#15382A', '#FBF6EB', 0.85));
    expect(composited).toBeCloseTo(7.14, 2);
    expect(contrastRatio(composite('#F3EEDF', '#15382A', 0.85), '#15382A')).toBeCloseTo(8.49, 2);
    // At 0.6 the two models disagree across the AA line — 3.53 against 5.03 —
    // so the reported ratio says which one the audit actually applies.
    const { failures } = auditContrast(css.replace('.today-btn:hover { opacity: 0.85; }', '.today-btn:hover { opacity: 0.6; }'));
    const hit = failures.find(f => f.key === 'light/-/.today-btn:hover@0.6/--color-nav-bg');
    expect(hit).toBeDefined();
    expect(hit.ratio).toBeCloseTo(3.53, 2);
  });

  test('an OPACITY_RULES entry the sheet no longer dims is reported', () => {
    const { failures } = auditContrast(css.replace('color: var(--color-brass-on-nav); opacity: 0.7;', 'color: var(--color-brass-on-nav);'));
    expect(keysOf(failures)).toContain('-/-/.nav-icon-btn/?');
  });

  test('a licensed literal does not licence the same colour elsewhere', () => {
    const { failures } = auditContrast(css + '\n.other-thing { color: #7A3030; }\n');
    expect(keysOf(failures)).toEqual(['-/-/.other-thing/?']);
  });

  test('a licence for a pair nothing measures any more is stale too', () => {
    // No season named "Ascension" exists, so this key is never measured.
    const key = 'dark/Ascension/--color-accent/--color-bg';
    withLicence(key, 999, () => {
      const { stale } = auditContrast(css);
      expect(keysOf(stale)).toContain(key);
    });
  });

  test('border-color and background-color are not read as foregrounds', () => {
    const { failures } = auditContrast(css + '\n.invented { border-color: var(--color-nav-bg); background-color: var(--color-heading); }\n');
    expect(failures).toEqual([]);
  });

  test('color: inherit is left to the rule that set the colour', () => {
    expect(auditContrast(css + '\n.invented { color: inherit; }\n').failures).toEqual([]);
  });
});
