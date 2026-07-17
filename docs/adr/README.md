# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [0001](./0001-pymupdf-for-style-classification.md) | Use PyMuPDF for PDF style classification | Proposed |
| [0002](./0002-two-pass-extraction-pdftotext-pymupdf.md) | Use pdftotext for text content; separate text from style | Proposed |
| [0003](./0003-content-based-page-detection.md) | Detect office page bounds from content, not hardcoded numbers | Proposed |
| [0004](./0004-unified-rendering-engine.md) | Single rendering engine with HTML and text output modes | Proposed |
| [0005](./0005-single-correction-manifest.md) | Single versioned manifest for all data corrections | Proposed |
| [0006](./0006-versioned-atomic-deploys.md) | Versioned directory deploys with staged promotion | Proposed |
| [0007](./0007-service-worker-offline-support.md) | Service worker with tiered caching for offline support | Proposed |

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

The review gate is: **all 7 Proposed ADRs must become Accepted before
implementation of any ADR begins.** This ensures no ADR is implemented against
the intent of another.

## Template
See [0000-template.md](./0000-template.md).
