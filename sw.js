const CACHE = 'uae-smart-observatory-v1';
const SHELL = ['/', '/assets/styles.css?v=1', '/assets/app.js?v=1', '/assets/background.svg?v=1', '/assets/uae-flag.svg?v=1'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).catch(() => null));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok && event.request.method === 'GET') {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then(r => r || caches.match('/')))
  );
});
