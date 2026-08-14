# Bundled fonts

Both families here are licensed under the SIL Open Font License 1.1, which
requires the licence to travel with the font files. The `.woff2` files are
served from `dist/` by every distribution channel — the static bucket, and the
native binaries via `npx cap sync` — so the licence files must be copied
alongside them. `tools/check_dist.py` asserts they are, and both channels reach
it: the bucket through `make deploy-staging`, the native projects through
`make mobile-sync`. Anything that populates `dist/` for distribution without
going through `check-dist` is a hole in that guarantee, not an exemption from it.

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

All of these are subsets, cut to the Latin range in the `unicode-range` the
faces declare. Subsetting is a modification the OFL permits; it does not use a
Reserved Font Name for anything new, and the `font-family` names in `fonts.css`
are the originals, matching the fonts they name.

Two provenances, which matters because only one is upstream bytes:

- The three variable faces are **Google Fonts subsets, taken as served**,
  vendored in a6a83be so the app works offline.
- `EBGaramond-600-smallcaps.woff2` was **re-subset locally** in 313c0c3 from the
  same Google source, keeping the `smcp`/`c2sc` features that `pyftsubset` drops
  by default. That is why it exists: without those features
  `font-variant: small-caps` is browser-synthesized rather than drawn. See
  `fonts.css` for which selectors reach it.

## Variable axes

Everything but the small-caps face is a variable font, so one file covers a
family+style at every weight:

| file | `wght` axis (min/def/max) |
|---|---|
| `EBGaramond-variable-regular.woff2` | 400 / 400 / 800 |
| `EBGaramond-variable-italic.woff2` | 400 / 400 / 800 |
| `IBMPlexSans-variable-regular.woff2` | 100 / 400 / 700 |
| `EBGaramond-600-smallcaps.woff2` | *(none — static instance at 600)* |

The `font-weight` descriptors in `fonts.css` state those ranges. Within a range,
adding a weight is a CSS change and not a new file — and a new file per weight
would reintroduce #108, where four declarations pointed at four byte-identical
copies of one variable font and a page using two weights fetched the same bytes
twice.

The small-caps face is the exception, and it fails quietly rather than loudly.
It is a static instance at 600, so widening its descriptor past `500 600` buys
nothing: the face still matches, the text still draws at 600, and nothing
reports a problem. A weight it cannot draw needs a new instance cut from the
source with `smcp`/`c2sc` kept, not a wider range.
