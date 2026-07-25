/**
 * The translation layer between this app's vocabulary and the Python core's.
 *
 * ────────────────────────────────────────────────────────────────────────────
 *  This file exists because the two were written independently and disagree.
 *  The app says `mobility` and `livesAlone`; the core says `mobility_limited`
 *  and `lives_alone`. That mismatch silently stopped the mobility interaction
 *  rule from ever firing in real onboarding — it only appeared to work when the
 *  core's spelling was typed by hand in a probe.
 *
 *  Every disagreement lives here, in one table, rather than being papered over
 *  at each call site. If a rule stops firing, this is the first place to look.
 * ────────────────────────────────────────────────────────────────────────────
 */

import type { RegionWeather } from './weather'
import type { RiskBand } from './risk'

/** App factor id → the core's `Condition` value. Only clinical conditions. */
const CONDITION_BY_FACTOR: Record<string, string> = {
  respiratory: 'respiratory',
  cardiovascular: 'cardiovascular',
  renal: 'renal',
  dementia: 'dementia',
}

/** App factor id → the core's person-level boolean name. */
const FLAG_BY_FACTOR: Record<string, string> = {
  mobility: 'mobility_limited',
  livesAlone: 'lives_alone',
}

export function conditionsFor(factors: string[]): string[] {
  return factors.map((f) => CONDITION_BY_FACTOR[f]).filter(Boolean)
}

export function flagsFor(factors: string[]): string[] {
  return factors.map((f) => FLAG_BY_FACTOR[f]).filter(Boolean)
}

/**
 * Reason codes the core would have raised for this person and this weather.
 *
 * The core derives these from a modelled indoor temperature it has and this app
 * does not, so these are approximations from outdoor observations. Each one is
 * commented with what it stands in for, because an approximation nobody can
 * audit is worse than an absence.
 */
export function exposureCodes(weather: RegionWeather, band: RiskBand): string[] {
  const codes: string[] = []

  // NIGHT_NO_RECOVERY — the core reads outdoor overnight minimum directly.
  if (weather.todayApparentMin >= 20) codes.push('night_no_recovery')

  // PEAK_HEAT — apparent peak at or above 30.
  if (weather.todayApparentMax >= 30) codes.push('peak_heat')

  // BEDROOM_WARM / BEDROOM_UNSAFE stand in for the FR-11 indoor estimate, which
  // this app has no equivalent of. Banding is the closest honest proxy: a
  // heat-high band means the bedroom is very likely past the comfortable range.
  if (band === 'heat-severe') codes.push('bedroom_unsafe')
  else if (band === 'heat-high' || band === 'heat-moderate') codes.push('bedroom_warm')

  // The cold codes map onto bands for the same reason.
  if (band === 'cold-severe') codes.push('indoor_below_12')
  else if (band === 'cold-high') codes.push('indoor_below_16')
  else if (band === 'cold-moderate') codes.push('indoor_below_18')

  return codes
}

/**
 * Every reason code active for this person right now — vulnerability and
 * exposure together. This is what the question bank selects against.
 */
export function activeCodes(input: {
  factors: string[]
  medClasses: string[]
  weather: RegionWeather
  band: RiskBand
}): string[] {
  const medCodes = input.medClasses.map((m) => `med_${m}`)
  const flagCodes = flagsFor(input.factors)
  return [
    ...conditionsFor(input.factors),
    ...flagCodes,
    ...medCodes,
    ...exposureCodes(input.weather, input.band),
  ]
}

/** Bands map onto the core's four tiers. */
export const TIER_FOR_BAND: Record<RiskBand, 'Low' | 'Elevated' | 'High' | 'Severe'> = {
  comfortable: 'Low',
  'cold-moderate': 'Elevated',
  'heat-moderate': 'Elevated',
  'cold-high': 'High',
  'heat-high': 'High',
  'cold-severe': 'Severe',
  'heat-severe': 'Severe',
}
