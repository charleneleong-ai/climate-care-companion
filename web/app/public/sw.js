/**
 * Minimal service worker.
 *
 * Two jobs: make the app installable to a phone home screen (Chrome requires a
 * fetch handler), and keep the shell usable on a bad connection. Weather is
 * deliberately network-first — stale temperatures are worse than no
 * temperatures for a safety app.
 */

const VERSION = 'climatise-v1'
const SHELL = [
  '/',
  '/companion',
  '/onboarding',
  '/manifest.webmanifest',
  '/data/uk-regions.geojson',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(VERSION)
      // Individual failures must not abort the whole install.
      .then((cache) => Promise.allSettled(SHELL.map((url) => cache.add(url))))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // Never cache API responses. Weather and advice must be current, and a
  // cached assistant reply would be actively misleading.
  if (url.pathname.startsWith('/api/')) return

  // Boundaries are immutable within a release — serve from cache immediately.
  if (url.pathname === '/data/uk-regions.geojson') {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ??
          fetch(request).then((res) => {
            const copy = res.clone()
            caches.open(VERSION).then((c) => c.put(request, copy))
            return res
          }),
      ),
    )
    return
  }

  // Everything else: network first, fall back to cache when offline.
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok && res.type === 'basic') {
          const copy = res.clone()
          caches.open(VERSION).then((c) => c.put(request, copy))
        }
        return res
      })
      .catch(() => caches.match(request).then((hit) => hit ?? caches.match('/'))),
  )
})

/**
 * Push. The reason this is an app and not a bookmark.
 *
 * The payload is rendered, never composed here — the body arrives already
 * approved and already through the SC-1 medication gate. A service worker that
 * writes its own clinical text would sit outside every safety check in the
 * system.
 */
self.addEventListener('push', (event) => {
  let payload = {}
  try {
    payload = event.data ? event.data.json() : {}
  } catch {
    // A push we cannot parse still means something happened. Better a vague
    // nudge to open the app than silence during a heat episode.
  }

  const title = payload.title || 'Climatise'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: payload.body || 'Your heat risk has changed. Open Climatise.',
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      // Severe overrides Do Not Disturb-adjacent quieting. Tier is carried
      // explicitly rather than inferred from the wording.
      requireInteraction: payload.tier === 'Severe',
      tag: payload.personId ? `climatise-${payload.personId}` : 'climatise',
      // Replace rather than stack: the current tier is the only one that matters,
      // and three stale notifications are how a phone gets muted.
      renotify: true,
      data: { url: payload.url || '/companion' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = event.notification.data?.url || '/companion'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      // Focus an open copy rather than opening a second one.
      for (const client of clients) {
        if (client.url.includes(target) && 'focus' in client) return client.focus()
      }
      return self.clients.openWindow(target)
    }),
  )
})
