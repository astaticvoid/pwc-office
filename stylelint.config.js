// Structural CSS checks for web/*.css.
//
// tools/validate_css.cjs already catches the failure that prompted it: an
// unclosed rule swallowing the rest of the sheet (#22). It reads braces, not
// CSS, so a misspelled property or a shorthand quietly overriding the
// declaration above it passes it. That is what this adds.
//
// The ruleset is deliberately small, on the same terms as eslint.config.js and
// ruff.toml: correctness only, and every rule passes on the sheet as it stands.
// stylelint-config-standard reports 163 problems here, almost all of them
// blank-line and one-declaration-per-line cosmetics — a linter that rewrites
// office.css to its own taste would be churn, not a gate.
export default {
  ignoreFiles: ['dist/**', 'node_modules/**', 'android/**', 'ios/**', 'boneyard/**'],
  rules: {
    // — does this name anything real? —
    'property-no-unknown': true,
    'unit-no-unknown': true,
    // color-mix builds the two theme grounds; audit_a11y.cjs mixes them in
    // OKLab the way the browser does.
    'function-no-unknown': [true, { ignoreFunctions: ['color-mix', 'light-dark'] }],
    'color-no-invalid-hex': true,
    'at-rule-no-unknown': true,
    'media-feature-name-no-unknown': true,
    'selector-pseudo-class-no-unknown': true,
    'selector-pseudo-element-no-unknown': true,
    'selector-type-no-unknown': true,
    // — is it silently overridden? —
    'declaration-block-no-duplicate-properties': [
      true,
      { ignore: ['consecutive-duplicates-with-different-values'] }, // property fallbacks
    ],
    'declaration-block-no-shorthand-property-overrides': true,
    'no-duplicate-selectors': true,
    'no-duplicate-at-import-rules': true,
    // — footguns —
    'no-invalid-double-slash-comments': true,
    'no-invalid-position-at-import-rule': true,
    'no-irregular-whitespace': true,
    'block-no-empty': true,
    'keyframe-declaration-no-important': true,
    'font-family-no-duplicate-names': true,
    'named-grid-areas-no-invalid': true,
    'string-no-newline': true,
  },
};
