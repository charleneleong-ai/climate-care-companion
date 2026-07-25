'use client'

/**
 * Client-side profile persistence. localStorage is the source of truth for
 * "who am I" so a returning user on the same phone skips onboarding entirely,
 * with no account and no network round trip.
 */

import { isValidProfile, type Profile } from './profile'

const KEY = 'climatise.profile'

export function loadProfile(): Profile | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return isValidProfile(parsed) ? parsed : null
  } catch {
    // Corrupt or blocked storage — treat as "not onboarded" rather than crashing.
    return null
  }
}

export function saveProfile(profile: Profile): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(KEY, JSON.stringify(profile))
  } catch {
    // Private browsing can reject writes. The session still works in memory.
  }
}

export function clearProfile(): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}

export function newProfileId(): string {
  // crypto.randomUUID needs a secure context; fall back for plain-http LAN testing.
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `p-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
