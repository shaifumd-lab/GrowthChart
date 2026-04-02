/**
 * Service Worker — offline caching for GrowthChart PWA.
 * Cache-first strategy: serve from cache, update in background.
 */

const CACHE_NAME = 'growthchart-v1';
const ASSETS = [
    '/',
    '/index.html',
    '/css/app.css',
    '/js/zscore-engine.js',
    '/js/data-store.js',
    '/js/file-access.js',
    '/js/app.js',
    '/js/chart-digitizer.js',
    '/manifest.json',
    // LMS data files
    '/data/cdc_hfa.json',
    '/data/cdc_hfa_infant.json',
    '/data/cdc_wfa.json',
    '/data/cdc_wfa_infant.json',
    '/data/cdc_bfa.json',
    '/data/who_hfa_boys_0_5.json',
    '/data/who_hfa_girls_0_5.json',
    '/data/who_hfa_boys_5_19.json',
    '/data/who_hfa_girls_5_19.json',
    '/data/who_wfa_boys_0_5.json',
    '/data/who_wfa_girls_0_5.json',
    '/data/who_bfa_boys_0_5.json',
    '/data/who_bfa_girls_0_5.json',
    '/data/who_bfa_boys_5_19.json',
    '/data/who_bfa_girls_5_19.json',
];

// External CDN resources (cached on first use)
const CDN_ASSETS = [
    'https://cdn.tailwindcss.com',
    'https://cdn.plot.ly/plotly-2.35.2.min.js',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(ASSETS);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Cache-first for local assets and CDN resources
    event.respondWith(
        caches.match(event.request).then(cached => {
            if (cached) return cached;

            return fetch(event.request).then(response => {
                // Cache CDN resources on first use
                if (response.ok && (url.origin === self.location.origin ||
                    CDN_ASSETS.some(cdn => event.request.url.startsWith(cdn)))) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            }).catch(() => {
                // Offline fallback
                if (event.request.mode === 'navigate') {
                    return caches.match('/index.html');
                }
                return new Response('Offline', { status: 503 });
            });
        })
    );
});
