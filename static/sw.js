// ============================================================
// SERVICE WORKER — BackStage Inventario
// Estrategia: Cache First para assets estáticos,
//             Network First para llamadas a la API.
// ============================================================

const CACHE_NAME = 'backstage-v10.20';

// Archivos que se pre-cachean al instalar la PWA
const ASSETS_TO_CACHE = [
    '/',
    '/assets/app.js',
    '/assets/manifest.json',
    '/assets/icons/favicon.ico',
    '/assets/icons/android-icon-192x192.png',
    '/assets/icons/android-icon-512x512.png',
    '/assets/icons/apple-icon-180x180.png',
    '/assets/imgs/login_transp.png',
    '/assets/imgs/backstage_horizontal_banner.png',
];

// ── INSTALL: pre-cachear assets esenciales ──────────────────
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Pre-cacheando assets...');
            return cache.addAll(ASSETS_TO_CACHE);
        })
    );
    self.skipWaiting();
});

// ── ACTIVATE: limpiar cachés antiguas ───────────────────────
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

// ── FETCH: estrategia según el tipo de request ──────────────
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Llamadas a la API → Network First (siempre datos frescos)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return new Response(
                    JSON.stringify({ error: 'Sin conexión. Verifica tu red.' }),
                    { status: 503, headers: { 'Content-Type': 'application/json' } }
                );
            })
        );
        return;
    }

    // Assets estáticos → Cache First
    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request).then((response) => {
                // Guardar en caché si la respuesta es válida
                if (response && response.status === 200 && response.type === 'basic') {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }
                return response;
            });
        })
    );
});
