'use strict';

const CACHE = 'pwc-v1';

// Shell files — updated frequently in development.
// Network-first: always try the network, fall back to cache if offline.
const NETWORK_FIRST = [
  '/app.js',
  '/render.js',
  '/office.css',
  '/manifest.json',
];

// Data + static assets — stable, large. Cache-first.
const CACHE_FIRST = [
  '/',
  '/data/offices.json',
  '/data/collects.json',
  '/data/season_bounds.json',
  '/data/psalter.json',
  '/data/fats/saints.json',
];

const PRECACHE = [...NETWORK_FIRST, ...CACHE_FIRST];

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
  if (evt.request.method !== 'GET') return;
  const url = new URL(evt.request.url);
  if (url.origin !== location.origin) return;

  const path = url.pathname;

  if (NETWORK_FIRST.includes(path)) {
    evt.respondWith(networkFirst(evt.request));
  } else {
    evt.respondWith(cacheFirst(evt.request));
  }
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
    return cached || new Response('Offline', { status: 503 });
  }
}

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
