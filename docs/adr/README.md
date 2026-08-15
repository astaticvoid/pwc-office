# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [0001](./0001-pymupdf-for-style-classification.md) | Use PyMuPDF for PDF style classification | Accepted |
| [0002](./0002-two-pass-extraction-pdftotext-pymupdf.md) | Use pdftotext for text content; separate text from style | Superseded |
| [0003](./0003-content-based-page-detection.md) | Detect office page bounds from content, not hardcoded numbers | Accepted |
| [0004](./0004-unified-rendering-engine.md) | Single rendering engine with HTML and text output modes | Accepted |
| [0005](./0005-single-correction-manifest.md) | Single versioned manifest for all data corrections | Accepted |
| [0006](./0006-versioned-atomic-deploys.md) | Versioned directory deploys with staged promotion | Accepted |
| [0007](./0007-service-worker-offline-support.md) | Browser cache and Capacitor bundle for offline support | Accepted |
| [0008](./0008-full-office-structured-output.md) | Full-office structured JSON output for validators | Accepted |
| [0009](./0009-automated-liturgical-quality-gating.md) | Automated liturgical quality gating with coherence scoring | Accepted |
| [0010](./0010-static-design-options-page.md) | Static design-options page for visual decision-making | Accepted |
| [0011](./0011-single-pass-fitz-no-casing-oracle.md) | Single-pass fitz extraction; no independent casing oracle | Accepted |
| [0012](./0012-editorial-breaks-vouched-by-the-manifest.md) | Editorial line breaks vouched for by the correction manifest, audited against the errata | Accepted |
| [0013](./0013-authorized-rubrics-are-rendered-not-curated.md) | Authorized rubrics are rendered, not curated | Accepted |
| [0014](./0014-optionality-is-presented-not-resolved.md) | Optionality is presented, not resolved | Accepted |
| [0015](./0015-provenance-for-app-authored-liturgical-text.md) | Provenance for app-authored liturgical text | Accepted |
| [0016](./0016-the-app-renders-the-rite-it-does-not-edit-it.md) | The app renders the authorized rite; it does not edit it | Accepted |
| [0017](./0017-secondary-observances-are-extracted-not-transcribed.md) | Secondary observances are extracted, not transcribed | Accepted |
| [0018](./0018-alternate-observance-toggle-presents-the-days-identity.md) | The alternate-observance toggle presents the day's identity | Accepted |
| [0019](./0019-settled-readings-of-the-rubrics.md) | Settled readings of the rubrics | Proposed |
| [0020](./0020-the-office-and-the-saints-fats-propers-are-extraction-only.md) | The product renders the office and the saints; FATS propers are extraction-only | Accepted |

## Status values
- **Proposed** — decision documented, awaiting review/adoption
- **Accepted** — agreed and in implementation
- **Deprecated** — superseded by a later ADR (but may still be in effect)
- **Superseded** — replaced by a later ADR and no longer in effect

## Review process
ADRs are reviewed by the project maintainer before acceptance. Review criteria:
1. The decision is clearly stated and motivated.
2. The consequences (positive and negative) are identified.
3. The ADR does not contradict an existing Accepted ADR.
4. Any contradiction with AGENTS.md or other project docs is explicitly
   acknowledged and resolved within the ADR.

Once Accepted, an ADR can be superseded by a later ADR that explicitly
references it. Superseded ADRs remain in the repository for historical context.
Deprecated ADRs are still in effect but are flagged for replacement.

The review gate is: **all Proposed ADRs must become Accepted before
implementation of any ADR begins.** This ensures no ADR is implemented against
the intent of another.
## Template
See [0000-template.md](./0000-template.md).
