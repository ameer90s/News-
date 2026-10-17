const CACHE = 'strategic-newsroom-v4';
const ASSETS = ['/', '/static/styles.css?v=2', '/static/app.js?v=2', '/static/icon.svg', '/static/background.webp?v=2', '/static/manifest.webmanifest'];
self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
  ]));
});
self.addEventListener('fetch', (e) => {
  if (e.request.url.includes('/api/')) return;
  // Network-first so visual updates are not stuck behind an old cached theme/background.
  e.respondWith(fetch(e.request).then((response) => {
    const copy = response.clone();
    caches.open(CACHE).then(cache => cache.put(e.request, copy));
    return response;
  }).catch(() => caches.match(e.request)));
});
