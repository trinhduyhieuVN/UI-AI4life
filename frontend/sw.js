/* Nasdaq Replay service worker: precache app shell, network-first + cache fallback,
   purge cache nq-* phiên bản cũ khi activate. /api/* luôn đi mạng (dữ liệu phiên không cache). */
const CACHE = 'nq-v2';
const PRECACHE = [
  '/', '/index.html', '/styles.css', '/manifest.webmanifest',
  '/icons/192.png', '/icons/512.png', '/icons/maskable-512.png',
  '/src/api.js', '/src/auth.js', '/src/data.js', '/src/main.js', '/src/prefs.js',
  '/src/roles.js', '/src/signals.js', '/src/sound.js', '/src/state.js', '/src/util.js', '/src/history.js', '/src/offline.js',
  '/src/chart/overlays.js', '/src/chart/renderer.js', '/src/chart/types.js', '/src/history-signals.js',
  '/src/ui/drawer.js', '/src/ui/menus.js', '/src/ui/migrate.js', '/src/ui/rail.js',
  '/src/ui/theme.js', '/src/ui/toasts.js', '/src/ui/transport.js',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('nq-') && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) {
    /* Chỉ 4 endpoint đọc bất biến (seed tất định) được cache-first + cập nhật ngầm;
       /auth, /prefs, /watchlist, /views, /reviews… luôn đi mạng. */
    if (/^\/api\/v1\/(symbols|sessions|bars|signals)$/.test(url.pathname)) e.respondWith(apiCacheFirst(e, req));
    return;
  }
  e.respondWith(
    fetch(req)
      .then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
        return res;
      })
      .catch(async () => {
        const hit = await caches.match(req);
        if (hit) return hit;
        if (req.mode === 'navigate') { const shell = await caches.match('/'); if (shell) return shell; }
        return Response.error();
      })
  );
});

async function apiCacheFirst(e, req) {
  const cache = await caches.open(CACHE);
  const refresh = fetch(req).then(res => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => null);
  e.waitUntil(refresh.then(() => {}));
  const hit = await cache.match(req);
  if (hit) return hit;
  return (await refresh) || Response.error();
}
