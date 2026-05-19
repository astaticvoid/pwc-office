'use strict';

const CACHE = 'pwc-v4';

// Shell + static data to pre-cache at install.
// Bump CACHE version above whenever these files change.
const PRECACHE = [
  '/',
  '/app.js',
  '/office.css',
  '/manifest.json',
  '/data/offices.json',
  '/data/collects.json',
  '/data/season_bounds.json',
  '/data/psalter.json',
];

self.addEventListener('install', evt => {
  evt.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener('activate', evt => {
  evt.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', evt => {
  // Only intercept same-origin GET requests.
  if (evt.request.method !== 'GET') return;
  const url = new URL(evt.request.url);
  if (url.origin !== location.origin) return;

  evt.respondWith(cacheFirst(evt.request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE);
    cache.put(request, response.clone());
  }
  return response;
}
