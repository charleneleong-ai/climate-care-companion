'use client'

import { useEffect } from 'react'

/**
 * Registers the service worker so the app can be installed to a phone home
 * screen. Renders nothing.
 *
 * Skipped in development — a caching service worker makes hot reload behave
 * unpredictably, and installability only matters for the deployed app.
 */
export default function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') return
    if (!('serviceWorker' in navigator)) return

    navigator.serviceWorker.register('/sw.js').catch((error) => {
      // Registration failing costs offline support, not the app.
      console.warn('[sw] registration failed', error)
    })
  }, [])

  return null
}
