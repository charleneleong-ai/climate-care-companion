/**
 * The client for the Python core.
 *
 * There is one risk model and it is not in this file — it is in
 * `packages/core`. This translates a Profile into the core's vocabulary, asks
 * it, and caches the answer.
 *
 * The cache is not an optimisation. NFR-04 requires the system to work with no
 * network by "serving last cached assessment" — a cache, not a recomputation.
 * That requirement is the reason the front end does not need its own engine,
 * and a cached answer keeps its `source`, so a stale figure never reads as
 * fresh. See docs/reconciliation.md.
 */

import { conditionsFor } from './codes'
import type { RegionWeather } from './weather'
import type { Profile } from './profile'

const CORE_URL = process.env.CORE_API_URL ?? 'http://127.0.0.1:8000'

export type Tier = 'Low' | 'Elevated' | 'High' | 'Severe'

export interface CoreReason {
  code: string
  title: string
  explanation: string
  weight: number
}

export interface CorePlanItem {
  code: string
  text: string
  watch_for: string | null
  escalate_to: string | null
  source: string
}

export interface CoreAssessment {
  person_id: string
  tier: Tier
  risk_score: number
  exposure_score: number
  vulnerability_score: number
  reasons: CoreReason[]
  exposure: {
    indoor_night_est_modelled: number
    indoor_day_est_modelled: number
    overnight_min: number
    peak_apparent: number
    peak_air: number
    spell_day: number
    dwelling_offset: number
    alert_level: string
    /** live | cache | archive | fixture. */
    source: string
  }
  plan: {
    audience: string
    items: CorePlanItem[]
    watch_points: string[]
    escalate_to: string[]
  }
  not_medical_advice: boolean
}

/**
 * Age. The core bands it; this app collects checkboxes.
 *
 * Ordered heaviest first, because 85+ carries the heaviest age weight in the
 * brief and someone who ticks both "over 75" and "over 85" means the latter.
 */
function ageBandFor(factors: string[]): string {
  if (factors.includes('over85')) return 'b85_plus'
  if (factors.includes('over75')) return 'b75_84'
  if (factors.includes('over65')) return 'b65_74'
  return 'under_65'
}

/**
 * Dwelling offset, from the one signal onboarding collects.
 *
 * "My home gets too hot" stands in for a top-floor south-facing flat until the
 * real dwelling fields exist. FR-11 wants type, floor and aspect; this is a
 * two-value approximation of a twenty-four-row lookup, and it is the largest
 * remaining gap between what the core can do and what this app asks for.
 */
const DEFAULT_DWELLING_OFFSET = 1.2
const OVERHEATING_OFFSET = 2.8

export function requestBodyFor(profile: Profile) {
  return {
    person: {
      id: profile.id,
      name: profile.name,
      age_band: ageBandFor(profile.factors),
      lives_alone: profile.factors.includes('livesAlone'),
      mobility_limited: profile.factors.includes('mobility'),
      conditions: conditionsFor(profile.factors),
      med_classes: profile.medClasses ?? [],
    },
    dwelling_offset: profile.factors.includes('overheatingHome')
      ? OVERHEATING_OFFSET
      : DEFAULT_DWELLING_OFFSET,
  }
}

/** Ask the core. Server-side only — CORE_URL is not public. */
export async function assessViaCore(profile: Profile): Promise<CoreAssessment> {
  const response = await fetch(`${CORE_URL}/assess`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(requestBodyFor(profile)),
    cache: 'no-store',
  })
  if (!response.ok) {
    throw new Error(`core returned ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as CoreAssessment
}

/** Weather is fetched separately, for display only. The core fetches its own,
 *  because it needs hourly data for FR-07 and this app does not. */
export type { RegionWeather }
