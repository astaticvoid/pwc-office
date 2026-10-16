import { describe, it, expect } from 'vitest';
import { renderScriptureReading } from '../../web/render.js';

describe('Scripture API v3 pure-data rendering (ADR 0025)', () => {
  it('renders standard reading using pure verses and chapter paragraphs', () => {
    const reading = {
      citation: 'Jn 1:1-2',
      book: 'John',
      verses: [
        { ch: 1, v: 1, text: 'In the beginning was the Word, and the Word was with God, and the Word was God.' },
        { ch: 1, v: 2, text: 'He was in the beginning with God.' },
      ],
      paragraphs: {
        '1': [1],
      },
      translation: 'nrsvue',
    };

    const html = renderScriptureReading(reading);
    expect(html).toBe(
      '<p class="scripture-block"><span class="scripture-ch-num">1</span> In the beginning was the Word, and the Word was with God, and the Word was God. <sup class="verse-num">2</sup>\u00A0He was in the beginning with God.</p>'
    );
  });

  it('respects paragraph boundaries across verses', () => {
    const reading = {
      citation: 'Test 1:1-3',
      book: 'Test',
      verses: [
        { ch: 1, v: 1, text: 'First verse.' },
        { ch: 1, v: 2, text: 'Second verse.' },
        { ch: 1, v: 3, text: 'Third verse start of new paragraph.' },
      ],
      paragraphs: {
        '1': [1, 3],
      },
      translation: 'nrsvue',
    };

    const html = renderScriptureReading(reading);
    const expected = [
      '<p class="scripture-block"><span class="scripture-ch-num">1</span> First verse. <sup class="verse-num">2</sup>\u00A0Second verse.</p>',
      '<p class="scripture-block"><sup class="verse-num">3</sup>\u00A0Third verse start of new paragraph.</p>',
    ].join('\n');

    expect(html).toBe(expected);
  });

  it('renders composite choice readings (" or ") cleanly', () => {
    const allReadings = {
      'Rom 5:1-2': {
        citation: 'Rom 5:1-2',
        book: 'Romans',
        verses: [
          { ch: 5, v: 1, text: 'Therefore, since we are justified by faith...' },
          { ch: 5, v: 2, text: 'through whom we have obtained access...' },
        ],
        paragraphs: { '5': [1] },
        translation: 'nrsvue',
      },
      'Gal 4:4-5': {
        citation: 'Gal 4:4-5',
        book: 'Galatians',
        verses: [
          { ch: 4, v: 4, text: 'But when the fullness of time had come...' },
          { ch: 4, v: 5, text: 'so that we might receive adoption as children.' },
        ],
        paragraphs: { '4': [1] },
        translation: 'nrsvue',
      },
    };

    const choiceReading = {
      citation: 'Rom 5:1-2 or Gal 4:4-5',
      book: 'Romans',
      verses: [...allReadings['Rom 5:1-2'].verses, ...allReadings['Gal 4:4-5'].verses],
      paragraphs: { '5': [1], '4': [1] },
      translation: 'nrsvue',
    };

    const html = renderScriptureReading(choiceReading, allReadings);
    expect(html).toContain('class="alt-block"');
    expect(html).toContain('class="alt-tabs" role="tablist"');
    expect(html).toContain('data-key="pwc-alt-reading-Rom 5:1-2-Gal 4:4-5"');
    expect(html).toContain('class="alt-source">Romans 5:1-2</p>');
    expect(html).toContain('class="alt-source">Galatians 4:4-5</p>');
    expect(html).toContain('Romans 5:1-2');
    expect(html).toContain('Galatians 4:4-5');
    expect(html).toContain('Therefore, since we are justified');
  });

  it('maintains backward compatibility with pre-rendered html if present', () => {
    const reading = {
      citation: 'Ps 23',
      book: 'Psalms',
      verses: [],
      html: '<p class="legacy">Pre-rendered HTML</p>',
      translation: 'kjv',
    };

    expect(renderScriptureReading(reading)).toBe('<p class="legacy">Pre-rendered HTML</p>');
  });

  it('preserves chapter sequence for readings spanning multiple chapters', () => {
    const reading = {
      citation: 'Jn 1:50-2:2',
      book: 'John',
      verses: [
        { ch: 1, v: 50, text: 'Jesus answered...' },
        { ch: 1, v: 51, text: 'Very truly I tell you...' },
        { ch: 2, v: 1, text: 'On the third day there was a wedding...' },
        { ch: 2, v: 2, text: 'Jesus and his disciples were also invited...' },
      ],
      paragraphs: {
        '1': [50],
        '2': [1],
      },
      translation: 'nrsvue',
    };

    const html = renderScriptureReading(reading);
    expect(html).toContain('<sup class="verse-num">50</sup>\u00A0Jesus answered');
    expect(html).toContain('<span class="scripture-ch-num">2</span> On the third day');
    expect(html.indexOf('Jesus answered')).toBeLessThan(html.indexOf('On the third day'));
  });

  it('renders both options even when allReadings has an unresolvable alternative', () => {
    const reading = {
      citation: 'Option A or Option B',
    };
    const allReadings = {
      'Option A': {
        citation: 'Option A',
        book: 'John',
        verses: [{ ch: 1, v: 1, text: 'First choice text' }],
      },
    };

    const html = renderScriptureReading(reading, allReadings);
    expect(html).toContain('class="alt-block"');
    expect(html).toContain('class="alt-tabs"');
    expect(html).toContain('First choice text');
    expect(html).toContain('Text unavailable: Option B');
  });

  it('renders Sirach 1:1-10, 18-27 starting from Chapter 1 verse 1 rather than the Prologue', () => {
    const reading = {
      citation: 'Sir 1:1-10, 18-27',
      book: 'Sirach',
      verses: [
        { ch: 1, v: 1, text: 'All wisdom is from the Lord, and with him it remains forever.' },
        { ch: 1, v: 2, text: 'The sand of the sea, the drops of rain, and the days of eternity—who can count them?' },
        { ch: 1, v: 10, text: 'upon all the living according to his gift; he lavished her upon those who love him.' },
        { ch: 1, v: 18, text: 'The fear of the Lord is the crown of wisdom, making peace and perfect health to flourish.' },
        { ch: 1, v: 27, text: 'For the fear of the Lord is wisdom and discipline; fidelity and humility are his delight.' },
      ],
      paragraphs: {},
      translation: 'nrsvue',
    };

    const html = renderScriptureReading(reading);
    expect(html).toContain('<span class="scripture-ch-num">1</span> All wisdom is from the Lord');
    expect(html).toContain('<sup class="verse-num">18</sup>\u00A0The fear of the Lord is the crown of wisdom');
    expect(html).toContain('<sup class="verse-num">27</sup>\u00A0For the fear of the Lord is wisdom');
    expect(html).not.toContain('Many great teachings');
  });
});
