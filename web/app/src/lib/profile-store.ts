/**
 * Server-side profile registry.
 *
 * Deliberately in-memory so the app runs with zero setup — clone, `npm run
 * dev`, and onboarding works. The client holds its own copy in localStorage
 * (see client-store.ts), so a serverless cold start losing this map does not
 * log anyone out; it only clears the shared roster.
 *
 * To make profiles durable, implement the four methods below against Postgres
 * and nothing else in the app has to change.
 */

import { DEMO_PROFILES, type Profile } from './profile'

export interface ProfileStore {
  get(id: string): Promise<Profile | undefined>
  save(profile: Profile): Promise<Profile>
  list(): Promise<Profile[]>
  remove(id: string): Promise<void>
}

class MemoryProfileStore implements ProfileStore {
  private profiles = new Map<string, Profile>()

  constructor(seed: Profile[] = []) {
    for (const p of seed) this.profiles.set(p.id, p)
  }

  async get(id: string) {
    return this.profiles.get(id)
  }

  async save(profile: Profile) {
    this.profiles.set(profile.id, profile)
    return profile
  }

  async list() {
    return [...this.profiles.values()].sort((a, b) => a.createdAt.localeCompare(b.createdAt))
  }

  async remove(id: string) {
    this.profiles.delete(id)
  }
}

/**
 * Hold the store on globalThis so Next's dev-mode hot reload does not wipe it
 * on every edit — a standard Next pattern for stateful singletons.
 */
const globalForStore = globalThis as unknown as { climatiseStore?: ProfileStore }

export function getProfileStore(): ProfileStore {
  if (!globalForStore.climatiseStore) {
    globalForStore.climatiseStore = new MemoryProfileStore(DEMO_PROFILES)
  }
  return globalForStore.climatiseStore
}
