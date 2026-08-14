# Bundled fonts

Both families here are licensed under the SIL Open Font License 1.1, which
requires the licence to travel with the font files. The `.woff2` files are
served from `dist/` by every distribution channel — the static bucket, and the
native binaries via `npx cap sync` — so the licence files must be copied
alongside them. `tools/check_dist.py` asserts they are.

The OFL text is reproduced verbatim from upstream; do not reflow or reformat it.

## EB Garamond — `OFL-EBGaramond.txt`

`EBGaramond-variable-regular.woff2`, `EBGaramond-variable-italic.woff2`,
`EBGaramond-600-smallcaps.woff2`

Embedded copyright: `Copyright 2017 The EB Garamond Project Authors
(https://github.com/octaviopardo/EBGaramond12)`

Licence text from `ofl/ebgaramond/OFL.txt` in <https://github.com/google/fonts>.

## IBM Plex Sans — `OFL-IBMPlexSans.txt`

`IBMPlexSans-variable-regular.woff2`

Embedded copyright: `Copyright 2019 IBM Corp. All rights reserved.` — the
upstream licence file carries the earlier `Copyright © 2017 IBM Corp. with
Reserved Font Name "Plex"` line. Same family, same licence; the bundled subsets
are from the later release.

Licence text from `ofl/ibmplexsans/OFL.txt` in <https://github.com/google/fonts>
(CRLF line endings, as distributed).

## Subsetting

These are Google Fonts `woff2` subsets, vendored in a6a83be so the app works
offline. Subsetting is a modification the OFL permits; it does not use a
Reserved Font Name for anything new, and the `font-family` names in `fonts.css`
are the originals, matching the fonts they name.

## Variable axes

Everything but the small-caps face is a variable font, so one file covers a
family+style at every weight:

| file | `wght` axis (min/def/max) |
|---|---|
| `EBGaramond-variable-regular.woff2` | 400 / 400 / 800 |
| `EBGaramond-variable-italic.woff2` | 400 / 400 / 800 |
| `IBMPlexSans-variable-regular.woff2` | 100 / 400 / 700 |
| `EBGaramond-600-smallcaps.woff2` | *(none — static instance at 600)* |

The `font-weight` descriptors in `fonts.css` state those ranges. Adding a weight
is a CSS change, not a new file — and a new file per weight would reintroduce
#108, where four declarations pointed at four byte-identical copies of one
variable font and a page using two weights fetched the same bytes twice.
