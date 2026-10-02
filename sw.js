/* ============================================================
   NOVEX AI v8.2 — Service Worker
   - Cache-first for static assets
   - Network-first for API
   - Offline fallback page
   - Auto-update with skipWaiting
   - Background sync ready
   ============================================================ */

const VERSION = 'novex-v8.2.0';
const STATIC_CACHE = `${VERSION}-static`;
const RUNTIME_CACHE = `${VERSION}-runtime`;
const API_CACHE = `${VERSION}-api`;
const OFFLINE_URL = '/offline.html';

/* Assets to pre-cache on install */
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/offline.html',
  '/themes.css',
  '/themes-extra.css',
  '/ui-modes.css',
  '/ui-modes.js',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon.svg'
];

/* Never cache these */
const NEVER_CACHE = [
  '/login',
  '/logout',
  '/auth/',
  '/chat-stream',
  '/register',
  '/me'
];

/* ============================================================
   INSTALL
   ============================================================ */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

/* ============================================================
   ACTIVATE — clean old caches
   ============================================================ */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => !k.startsWith(VERSION))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

/* ============================================================
   FETCH — smart routing
   ============================================================ */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only same-origin + https
  if (url.origin !== self.location.origin) return;

  // Skip non-GET
  if (request.method !== 'GET') return;

  // Skip auth + streaming
  if (NEVER_CACHE.some((p) => url.pathname.startsWith(p))) return;

  // API: network-first with short cache
  if (url.pathname.startsWith('/api') ||
      url.pathname.startsWith('/chats') ||
      url.pathname.startsWith('/models') ||
      url.pathname.startsWith('/settings') ||
      url.pathname.startsWith('/personas') ||
      url.pathname.startsWith('/memory') ||
      url.pathname.startsWith('/projects') ||
      url.pathname.startsWith('/stats') ||
      url.pathname.startsWith('/gamification') ||
      url.pathname.startsWith('/flashcards') ||
      url.pathname.startsWith('/docs') ||
      url.pathname.startsWith('/languages') ||
      url.pathname.startsWith('/voices') ||
      url.pathname.startsWith('/health') ||
      url.pathname === '/me') {
    event.respondWith(networkFirstApi(request));
    return;
  }

  // Static assets: cache-first
  if (
    request.destination === 'style' ||
    request.destination === 'script' ||
    request.destination === 'image' ||
    request.destination === 'font' ||
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.jpg') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.woff2')
  ) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // HTML navigations: network-first with offline fallback
  if (request.mode === 'navigate' || request.destination === 'document') {
    event.respondWith(networkFirstHtml(request));
    return;
  }

  // Default: try network, fallback to cache
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});

/* ============================================================
   STRATEGIES
   ============================================================ */
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const res = await fetch(request);
    if (res && res.status === 200 && res.type === 'basic') {
      const cache = await caches.open(cacheName);
      cache.put(request, res.clone());
    }
    return res;
  } catch (e) {
    return caches.match(OFFLINE_URL);
  }
}

async function networkFirstApi(request) {
  try {
    const res = await fetch(request);
    if (res && res.status === 200) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, res.clone());
    }
    return res;
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) {
      // Add header to indicate offline
      const headers = new Headers(cached.headers);
      headers.set('X-From-Cache', '1');
      return new Response(await cached.blob(), {
        status: cached.status,
        statusText: cached.statusText,
        headers,
      });
    }
    return new Response(
      JSON.stringify({ error: 'offline', offline: true }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function networkFirstHtml(request) {
  try {
    const res = await fetch(request);
    if (res && res.status === 200) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, res.clone());
    }
    return res;
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) return cached;
    const offline = await caches.match(OFFLINE_URL);
    return offline || new Response('Offline', { status: 503 });
  }
}

/* ============================================================
   MESSAGES (from page)
   ============================================================ */
self.addEventListener('message', (event) => {
  const { data } = event;
  if (!data || typeof data !== 'object') return;

  switch (data.type) {
    case 'SKIP_WAITING':
      self.skipWaiting();
      break;
    case 'CLEAR_CACHE':
      caches.keys().then((keys) =>
        Promise.all(keys.map((k) => caches.delete(k)))
      ).then(() => {
        event.source?.postMessage({ type: 'CACHE_CLEARED' });
      });
      break;
    case 'CACHE_URLS':
      if (Array.isArray(data.urls)) {
        caches.open(RUNTIME_CACHE).then((cache) => cache.addAll(data.urls));
      }
      break;
  }
});

/* ============================================================
   PUSH NOTIFICATIONS
   ============================================================ */
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let payload = {};
  try { payload = event.data.json(); }
  catch { payload = { title: 'NOVEX AI', body: event.data.text() }; }

  const options = {
    body: payload.body || '',
    icon: payload.icon || '/icons/icon-192.png',
    badge: '/icons/badge-72.png',
    vibrate: [100, 50, 100],
    data: payload.data || {},
    actions: payload.actions || [
      { action: 'open', title: 'Open' },
      { action: 'dismiss', title: 'Dismiss' }
    ],
    tag: payload.tag || 'novex-notification',
    renotify: true
  };
  event.waitUntil(
    self.registration.showNotification(payload.title || 'NOVEX AI', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const action = event.action;
  if (action === 'dismiss') return;
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            client.navigate(url);
            return client.focus();
          }
        }
        if (self.clients.openWindow) return self.clients.openWindow(url);
      })
  );
});

/* ============================================================
   BACKGROUND SYNC
   ============================================================ */
self.addEventListener('sync', (event) => {
  if (event.tag === 'novex-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

async function doBackgroundSync() {
  // Placeholder: replay queued requests
  // In future: read IndexedDB queue, retry fetches
  return;
}

/* ============================================================
   PERIODIC BACKGROUND SYNC (experimental)
   ============================================================ */
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'novex-refresh') {
    event.waitUntil(refreshCache());
  }
});

async function refreshCache() {
  const urls = ['/health', '/models'];
  try {
    const cache = await caches.open(API_CACHE);
    await Promise.all(
      urls.map(async (u) => {
        try {
          const res = await fetch(u, { credentials: 'include' });
          if (res.ok) cache.put(u, res.clone());
        } catch {}
      })
    );
  } catch {}
}