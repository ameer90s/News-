/* مرصد الإمارات الذكي — Service Worker. ارفع VERSION مع كل إصدار (tools/bump_version.py). */
const VERSION = '1.0.2';
const CACHE = 'mirsad-' + VERSION;
const SHELL = [
  '/',
  '/style.css?v=' + VERSION,
  '/app.js?v=' + VERSION,
  '/bg-news.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: 'reload' }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('mirsad-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;          // fonts etc. stay with the browser
  if (url.pathname.startsWith('/api/')) return;              // API responses are never cached here
  if (url.pathname === '/sw.js') return;

  if (req.mode === 'navigate') {                             // HTML: network first, cache only when offline
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put('/', copy)).catch(() => {});
        return res;
      }).catch(() => caches.match('/'))
    );
    return;
  }

  // Versioned static assets (?v=) and the locked background: cache first.
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    }))
  );
});
