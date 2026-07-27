#!/usr/bin/env node
/**
 * tools/validate_css.cjs — structural CSS validity check.
 *
 * Plain CSS (no preprocessor, no bundler in this project) never allows a
 * style rule nested inside another style rule's declaration block — only
 * `@media`/`@supports`/`@document`/`@layer`/`@container` bodies (which hold
 * further style rules) and `@keyframes` bodies (which hold percentage/
 * from/to selector blocks) may contain nested rules. A stray, unclosed
 * brace produces exactly this shape by accident, and because every rule
 * after it still opens and closes evenly, brace-balance alone doesn't
 * always surface it before end-of-file — this happened for real: an
 * orphaned `.day-ctrl-seg {` in web/office.css swallowed the entire rest
 * of the file (loading/error states, the whole desktop layout, print
 * styles, the eval banner) for about a week with zero test failures,
 * because nothing in this project validates CSS syntax at all. See
 * BUGS.md 2026-07-27.
 *
 * Two checks, in order:
 *   1. A style rule nested inside another style rule's declaration block —
 *      reported immediately, at the exact line, with both rule's selectors.
 *   2. Brace balance at end-of-file (unclosed rule, or a stray extra `}`) —
 *      a second net for anything the first check doesn't classify.
 *
 * Usage: node tools/validate_css.cjs [--json]
 */

const { readdirSync, readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

// At-rules whose body holds further style rules (media-query-like).
const NESTING_ATRULES = new Set(['media', 'supports', 'document', 'layer', 'container']);
// At-rules whose body holds selector blocks (0%, 50%, from, to), each a
// normal declaration block one level down.
const KEYFRAMES_ATRULES = new Set(['keyframes', '-webkit-keyframes', '-moz-keyframes']);

function stripCommentsAndStrings(css) {
  // Replace comment/string contents with spaces (same length, so line/column
  // tracking and reported snippets from the original text stay correct),
  // so braces or quote characters inside them can't confuse the tokenizer.
  let out = '';
  let i = 0;
  const n = css.length;
  while (i < n) {
    const c = css[i];
    if (c === '/' && css[i + 1] === '*') {
      const end = css.indexOf('*/', i + 2);
      const stop = end === -1 ? n : end + 2;
      for (let j = i; j < stop; j++) out += css[j] === '\n' ? '\n' : ' ';
      i = stop;
      continue;
    }
    if (c === '"' || c === "'") {
      const quote = c;
      let j = i + 1;
      while (j < n && css[j] !== quote) {
        if (css[j] === '\\') j++; // skip escaped char
        j++;
      }
      const stop = Math.min(j + 1, n);
      for (let k = i; k < stop; k++) out += css[k] === '\n' ? '\n' : ' ';
      i = stop;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

function validateCss(css, filename) {
  const clean = stripCommentsAndStrings(css);
  const errors = [];
  const stack = []; // { kind: 'declaration'|'atrule-nesting'|'atrule-keyframes', selector, line }
  let buf = '';
  let line = 1;

  for (let i = 0; i < clean.length; i++) {
    const c = clean[i];
    if (c === '\n') line++;

    if (c === '{') {
      const selector = buf.trim().replace(/\s+/g, ' ');
      buf = '';
      const parent = stack[stack.length - 1];

      if (selector.startsWith('@')) {
        const name = (selector.match(/^@([-\w]+)/) || [, ''])[1].toLowerCase();
        if (NESTING_ATRULES.has(name)) {
          stack.push({ kind: 'atrule-nesting', selector, line });
        } else if (KEYFRAMES_ATRULES.has(name)) {
          stack.push({ kind: 'atrule-keyframes', selector, line });
        } else {
          // @font-face, @page, @property, etc. — declaration-only body.
          stack.push({ kind: 'declaration', selector, line });
        }
        continue;
      }

      if (parent && parent.kind === 'declaration') {
        errors.push(
          `${filename}:${line}: style rule "${selector}" nested inside "${parent.selector}"` +
          ` (opened at line ${parent.line}) — plain CSS doesn't allow this;` +
          ` almost certainly a missing "}" before this line.`
        );
      }

      const kind = parent && parent.kind === 'atrule-keyframes' ? 'declaration'
        : parent && parent.kind === 'atrule-nesting' ? 'declaration'
        : 'declaration';
      stack.push({ kind, selector, line });
      continue;
    }

    if (c === '}') {
      if (stack.length === 0) {
        errors.push(`${filename}:${line}: unexpected "}" with no open rule to close.`);
      } else {
        stack.pop();
      }
      buf = '';
      continue;
    }

    if (c === ';') {
      buf = '';
      continue;
    }

    buf += c;
  }

  if (stack.length > 0) {
    const unclosed = stack[0];
    errors.push(
      `${filename}: ${stack.length} unclosed rule(s) at end of file — ` +
      `outermost is "${unclosed.selector}" opened at line ${unclosed.line}.`
    );
  }

  return errors;
}

function main() {
  const useJson = process.argv.includes('--json');
  const webDir = join(root, 'web');
  const files = readdirSync(webDir).filter(f => f.endsWith('.css'));

  const errors = [];
  for (const file of files) {
    const css = readFileSync(join(webDir, file), 'utf8');
    errors.push(...validateCss(css, file));
  }

  if (useJson) {
    console.log(JSON.stringify({
      files_checked: files.length,
      errors,
      error_count: errors.length,
    }, null, 2));
    process.exit(errors.length ? 1 : 0);
  }

  console.log(`CSS structural validity check: ${files.length} file(s)`);
  if (errors.length === 0) {
    console.log('All stylesheets parse cleanly.');
    return;
  }

  console.log(`\n${errors.length} error(s):\n`);
  for (const e of errors) console.log(`  ${e}`);
  process.exit(1);
}

main();
