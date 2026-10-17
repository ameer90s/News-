// v11 — the old precache list pointed to /static/... files that no longer exist in this
// flat build, so every new service worker failed to install and phones could stay on an
// older cached version of the page. Paths below match the flat routes in app.py.
const CACHE = 'uae-monitor-v11';
const ASSETS = ['/', '/styles.css?v=11', '/app.js?v=11', '/icon.svg', '/background.webp', '/manifest.webmanifest'];
self.addEventListener('install', (e) => {
  self.skipWaiting();
  // Cache each file on its own so one missing file can never block the update.
  e.waitUntil(caches.open(CACHE).then((cache) => Promise.all(ASSETS.map((url) => cache.add(url).catch(() => null)))));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
  ]));
});
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/')) return;
  // Network-first so visual updates are not stuck behind an old cached theme/background.
  e.respondWith(fetch(e.request).then((response) => {
    if (response && (response.ok || response.type === 'opaque')) {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(e.request, copy));
    }
    return response;
  }).catch(() => caches.match(e.request).then((hit) => hit || (e.request.mode === 'navigate' ? caches.match('/') : undefined))));
});
