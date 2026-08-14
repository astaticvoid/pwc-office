# Bundled fonts

Both families here are licensed under the SIL Open Font License 1.1, which
requires the licence to travel with the font files. The `.woff2` files are
served from `dist/` by every distribution channel — the static bucket, and the
native binaries via `npx cap sync` — so the licence files must be copied
alongside them. `tools/check_dist.py` asserts they are.

The OFL text is reproduced verbatim from upstream; do not reflow or reformat it.

## EB Garamond — `OFL-EBGaramond.txt`

`EBGaramond-{400,500}-italic.woff2`,
`EBGaramond-{400,500,600,700}-regular.woff2`,
`EBGaramond-600-smallcaps.woff2`

Embedded copyright: `Copyright 2017 The EB Garamond Project Authors
(https://github.com/octaviopardo/EBGaramond12)`

Licence text from `ofl/ebgaramond/OFL.txt` in <https://github.com/google/fonts>.

## IBM Plex Sans — `OFL-IBMPlexSans.txt`

`IBMPlexSans-{400,500,600,700}-regular.woff2`

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
