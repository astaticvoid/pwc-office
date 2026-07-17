# ADR 0007: Browser cache and Capacitor bundle for offline support

## Status
Proposed

## Context
The Daily Office is a static SPA — all assets are JSON, JS, CSS, and HTML files
served from a single origin. Browser HTTP cache handles these naturally: on
first visit the browser caches every asset by URL. On subsequent visits (even
offline), cached assets serve from disk.

For mobile, Capacitor bundles the entire `dist/` directory into the native app
binary. No network requests are needed for any app functionality — the app
launches and renders the Daily Office entirely from local files.

A previous service worker implementation was removed (it cached `app.js`
aggressively, causing stale-code/current-data mismatches on deploy). The current
`web/sw.js` is a kill-switch: it exists solely to unregister itself and clear
residual caches from that old implementation.

## Decision
**No service worker.** Browser HTTP cache and Capacitor bundling provide
sufficient offline support for both the web and mobile targets. The kill-switch
SW is retained to clean up old installs.

Rationale:
- The web app is entirely static assets — browser cache is the correct
  mechanism for static assets.
- The Capacitor shell bundles `dist/` at build time — every file is local.
- A service worker would add complexity (lifecycle management, cache
  invalidation, cross-browser quirks) for no additional offline capability
  beyond what the browser already provides.
- The prior SW failure (stale-code/current-data mismatch) is a well-understood
  caching-strategy error that doesn't need a fix — it needs no SW at all.

## Consequences

### Positive
- No service worker complexity. The kill-switch SW remains (~20 lines).
- Browser cache handles offline automatically for returning visitors.
- Capacitor handles offline for mobile users.
- No version-manifest generation step needed at build time.
- No cache-invalidation logic in the app shell.

### Negative
- No offline indicator banner (the browser shows its own offline UI).
- No programmatic cache invalidation — stale caches resolve when the browser
  decides, not when the app decides. For a static site with deploy-driven
  URL changes (versioned deploys per ADR 0006), this is acceptable: new
  deploy → new origin path → new URLs → browser treats them as new resources.
- First-time visitors without connectivity see a browser error page. Returning
  visitors (the common case for a daily-use app) see cached content.
