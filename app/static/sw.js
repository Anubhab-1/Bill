/**
 * Mall Billing System — Service Worker
 * =====================================
 * Strategy:
 *   - Static assets (CSS/JS/fonts/images): Cache-first, update in background.
 *   - Navigation / HTML pages: Network-first. Fall back to /offline if no network.
 *   - API JSON: Network-first with short timeout; no offline cache.
 *
 * Cache versioning: bump CACHE_VERSION when deploying breaking changes.
 */

const CACHE_VERSION = 'v1.1.0';
const SHELL_CACHE = `mall-shell-${CACHE_VERSION}`;
const STATIC_CACHE = `mall-static-${CACHE_VERSION}`;

// Core app shell — always cached on install
const SHELL_URLS = [
    '/offline',
];

// Static assets to pre-cache (cache-first forever until version bump)
const STATIC_EXTENSIONS = ['.css', '.js', '.woff', '.woff2', '.ttf', '.png', '.jpg', '.svg', '.ico', '.webp'];

// ── Install ────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(SHELL_CACHE).then(cache => cache.addAll(SHELL_URLS))
    );
    self.skipWaiting();
});

// ── Activate — clean up old caches ───────────────────────────────────────
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(k => k !== SHELL_CACHE && k !== STATIC_CACHE)
                    .map(k => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

// ── Fetch ─────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // Only intercept same-origin requests
    if (url.origin !== self.location.origin) return;

    // Skip non-GET requests
    if (request.method !== 'GET') return;

    // Skip API routes — always network only
    if (url.pathname.startsWith('/reporting/api/') ||
        url.pathname.startsWith('/billing/api/') ||
        url.pathname.startsWith('/inventory/api/')) return;

    const isStaticAsset = STATIC_EXTENSIONS.some(ext => url.pathname.endsWith(ext)) ||
        url.pathname.startsWith('/static/');

    if (isStaticAsset) {
        // Cache-first for static assets
        event.respondWith(cacheFirst(request, STATIC_CACHE));
    } else {
        // Network-first for HTML pages — fall back to /offline
        event.respondWith(networkFirstWithOfflineFallback(request));
    }
});

// ── Background Sync ───────────────────────────────────────────────────────
self.addEventListener('sync', event => {
    if (event.tag === 'sync-sales') {
        console.log('SW: Background sync triggered for "sync-sales"');
        event.waitUntil(syncOfflineData());
    }
});

/**
 * Communicates with the client (pwa.js) to trigger the sync.
 * Since SW doesn't have direct access to IndexedDB in many old browsers 
 * or it's cleaner to let pwa.js handle the domain-specific POSTs.
 */
async function syncOfflineData() {
    const clients = await self.clients.matchAll();
    for (const client of clients) {
        client.postMessage({ type: 'TRIGGER_SYNC' });
    }
}

// ── Cache-first strategy ───────────────────────────────────────────────────
async function cacheFirst(request, cacheName) {
    const cached = await caches.match(request);
    if (cached) return cached;
    try {
        const response = await fetch(request);
        if (response && response.status === 200) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
        }
        return response;
    } catch {
        return new Response('', { status: 503, statusText: 'Service Unavailable' });
    }
}

// ── Network-first with offline fallback ───────────────────────────────────
async function networkFirstWithOfflineFallback(request) {
    try {
        const response = await Promise.race([
            fetch(request),
            new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 8000))
        ]);
        // Avoid caching HTML navigations to prevent stale authenticated pages.
        return response;
    } catch {
        // Try cache first
        const cached = await caches.match(request);
        if (cached) return cached;
        // Last resort: offline page
        const offlinePage = await caches.match('/offline');
        return offlinePage || new Response('<h1>You are offline</h1>', {
            status: 503,
            headers: { 'Content-Type': 'text/html' }
        });
    }
}
