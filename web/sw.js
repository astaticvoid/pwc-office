// Kill-switch: unregisters this service worker and clears all caches.
// Deployed once to clean up existing installs; app.js no longer registers a SW.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', async () => {
  await caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))));
  await self.registration.unregister();
  (await self.clients.matchAll({ type: 'window' })).forEach(c => c.navigate(c.url));
});
