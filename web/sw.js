'use strict';

const CACHE = 'pwc-v1'; // make build stamps this with a content hash

// Shell files cached on install. index.html ('/')  is intentionally excluded —
// it must always be fetched from the network so a stale CF edge never poisons
// the SW cache with an old HTML structure (e.g. missing type="module").
const SHELL = [
  '/app.js',
  '/render.js',
  '/office.css',
  '/manifest.json',
  '/data/offices.json',
  '/data/collects.json',
  '/data/season_bounds.json',
  '/data/psalter.json',
  '/data/fats/saints.json',
];

self.addEventListener('install', evt => {
  evt.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(SHELL))
  );
  // No self.skipWaiting() — new SW waits until all tabs running the old SW
  // are closed. This prevents the stale-HTML / module-import race on deploy.
});

self.addEventListener('activate', evt => {
  evt.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', evt => {
  if (evt.request.method !== 'GET') return;
  const url = new URL(evt.request.url);
  if (url.origin !== location.origin) return;

  // Never intercept index.html — let the browser fetch it fresh every time.
  if (url.pathname === '/' || url.pathname === '/index.html') return;

  // Everything else: network-first with cache fallback (offline support).
  evt.respondWith(networkFirst(evt.request));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached ?? new Response('Offline', { status: 503 });
  }
}
