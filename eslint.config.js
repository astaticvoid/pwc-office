import js from '@eslint/js';
import globals from 'globals';

// Flat config for the whole repo. Three runtimes and two module systems:
//   - web/*.js            — browser ESM (no build step)
//   - cli/*.js            — Node ESM
//   - tools/*.cjs         — Node CommonJS (QA + extraction tooling)
//   - tools/test_*.js     — Node ESM (test orchestrators)
//   - tests/**            — Vitest + Playwright ESM (.js resolves as ESM under
//                           "type": "module"; test files do `window`/`document`
//                           inside page.evaluate callbacks, hence browser globals)
//   - infra/**            — CloudFront Functions (cloudfront-js-2.0 runtime)
//
// The ruleset is deliberately small ("non-bloat"): correctness + dead code +
// a few low-noise formatting guards the codebase already complies with, so the
// linter stops drift rather than churning the tree. Add a rule only if it
// catches a real class of mistake and the existing code passes it.
export default [
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      '.venv/**',
      'test-results/**',
      'playwright-report/**',
      '.build/**',
      'boneyard/**',
      'android/**',
      'ios/**',
      'sources/**',
      'data/**', // symlinked pipeline output; not app source
      'web/data/**',
    ],
  },

  js.configs.recommended,

  // Shared rules across every JS dialect in the tree.
  {
    files: ['**/*.js', '**/*.cjs'],
    rules: {
      // — dead code & correctness —
      'no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrors: 'none', // `catch (_) {}` is the intentional ignore idiom here
        },
      ],
      'no-unreachable': 'error',
      'no-constant-condition': 'error',
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      // — formatting drift guards (semicolons, trailing commas, edge whitespace)
      // — `quotes` is deliberately absent: the tree mixes single for JS and
      //    double for HTML/browser-eval strings, both intentional.
      semi: ['error', 'always'],
      // Trailing commas in multiline arrays/objects/imports (which the tree
      // uses), but NOT in function calls (e.g. `.some(fn)`).
      'comma-dangle': [
        'error',
        {
          arrays: 'always-multiline',
          objects: 'always-multiline',
          imports: 'always-multiline',
          exports: 'always-multiline',
          functions: 'ignore',
        },
      ],
      'no-trailing-spaces': 'error',
      'eol-last': ['error', 'always'],
      // — footguns —
      'no-case-declarations': 'error',
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-sparse-arrays': 'error',
    },
  },

  // Browser ESM — web/ (render.js is shared with Node but only touches guarded
  // globals, so browser + node globals together keep it a single source).
  {
    files: ['web/**/*.js'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ['web/sw.js'],
    languageOptions: { globals: { ...globals.browser, ...globals.serviceworker } },
  },

  // Node — cli/ and the no-build test orchestrators, plus repo-root configs.
  {
    files: ['cli/**/*.js', 'tools/test_*.js', '*.config.js', 'eslint.config.js'],
    languageOptions: { globals: globals.node },
  },

  // Node CommonJS — QA + extraction tooling (sourceType: "commonjs" so
  // `require`/`module` resolve without globals gymnastics).
  {
    files: ['**/*.cjs'],
    languageOptions: { sourceType: 'commonjs', globals: globals.node },
  },
  // compare_staging reaches into the browser via page.evaluate.
  {
    files: ['tools/compare_staging.cjs'],
    languageOptions: { sourceType: 'commonjs', globals: { ...globals.node, ...globals.browser } },
  },

  // Vitest + Playwright — browser globals appear inside page.evaluate callbacks.
  {
    files: ['tests/**/*.js'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },

  // CloudFront Functions run on the cloudfront-js-2.0 runtime, not Node: no
  // imports, `var`, double quotes, and `handler` is discovered by name (not
  // exported). Keep syntax checks, drop the style/dead-code rules that assume
  // a Node/bundler idiom.
  {
    files: ['infra/**/*.js'],
    rules: {
      'no-unused-vars': 'off',
      semi: 'off',
      'comma-dangle': 'off',
    },
  },
];
