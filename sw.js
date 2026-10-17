const CACHE = 'strategic-newsroom-v11';
const ASSETS = [
  '/',
  '/styles.css?v=11',
  '/app.js?v=11',
  '/icon.svg',
  '/background.webp',
  '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))),
  ]));
});

self.addEventListener('fetch', (e) => {
  if (e.request.url.includes('/api/')) return;

  e.respondWith(
    fetch(e.request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(e.request, copy));
      return response;
    }).catch(() => caches.match(e.request))
  );
});
