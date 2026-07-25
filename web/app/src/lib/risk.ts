/**
 * Risk banding — the seam between the data layer and the advice layer.
 *
 * ────────────────────────────────────────────────────────────────────────────
 *  FOR WHOEVER IS WRITING THE ADVICE CONTENT:
 *
 *  You do not need to read weather APIs or touch the map. This module turns
 *  (weather + profile) into a structured `RiskAssessment`. Write your advice
 *  against that type in `advice.ts` — nothing else needs to change.
 *
 *  Everything you need is on the assessment:
 *    band         → which of 7 bands (cold-severe … heat-severe)
 *    severity     → 0-100, for ordering/urgency within a band
 *    drivers      → *why* it banded that way (the hooks for specific advice)
 *    thresholds   → this person's personalised cut-offs, already adjusted
 *    headroom     → °C until the next band up/down (for "it's about to…")
 * ────────────────────────────────────────────────────────────────────────────
 */

import {
  type InteractionRule,
  matchingInteractions,
  medicationBurden,
} from './clinical'
import type { Profile } from './profile'
import type { RegionWeather } from './weather'

export type RiskBand =
  | 'cold-severe'
  | 'cold-high'
  | 'cold-moderate'
  | 'comfortable'
  | 'heat-moderate'
  | 'heat-high'
  | 'heat-severe'

export type RiskDirection = 'cold' | 'heat' | 'none'

/** A specific reason this person is at elevated risk right now. */
export interface RiskDriver {
  /** Stable id — key your advice copy off this, not the label. */
  id: string
  /** Short human-readable reason. */
  label: string
  /** How much this contributed, 0-1, for ranking which advice to lead with. */
  weight: number
}

export interface PersonalThresholds {
  /** Below this apparent temp = severe cold risk. */
  coldSevere: number
  coldHigh: number
  coldModerate: number
  heatModerate: number
  heatHigh: number
  /** Above this apparent temp = severe heat risk. */
  heatSevere: number
}

export interface RiskAssessment {
  band: RiskBand
  direction: RiskDirection
  /** 0-100. 0 = perfectly comfortable, 100 = maximum modelled danger. */
  severity: number
  /** Ranked most-important-first. */
  drivers: RiskDriver[]
  thresholds: PersonalThresholds
  /** °C of margin before this person crosses into the next band up in severity. */
  headroomToNextBand: number
  /** The temperature the banding was actually computed from (apparent, °C). */
  effectiveTemperature: number
  /** True when today's forecast crosses a worse band than right now. */
  worseningToday: boolean
  /** Echoed through so advice and UI never disagree about the inputs. */
  weather: RegionWeather
  profileId: string
  /**
   * Combination rules that fire for this person in this weather.
   *
   * Computed here rather than in advice.ts because this is where the profile is
   * in scope, and because they are part of the assessment: "heat plus a water
   * tablet plus reduced kidney function" is a finding, not a phrasing choice.
   */
  interactions: InteractionRule[]
}

/** Bands map onto the Python tiers so the shared interaction rules can gate on
 *  severity without this file needing to know what a tier is. */
const TIER_FOR_BAND: Record<RiskBand, InteractionRule['min_tier']> = {
  comfortable: 'Low',
  'cold-moderate': 'Elevated',
  'heat-moderate': 'Elevated',
  'cold-high': 'High',
  'heat-high': 'High',
  'cold-severe': 'Severe',
  'heat-severe': 'Severe',
}

/**
 * Baseline thresholds for a healthy adult, in apparent (feels-like) °C.
 *
 * Anchored on UKHSA Cold-Health and Heat-Health Alert guidance: sustained
 * exposure below ~5°C and above ~27°C is where excess-mortality signal starts
 * appearing in England. These are deliberately conservative for the low end
 * because UK housing stock heats poorly.
 */
const BASELINE: PersonalThresholds = {
  coldSevere: 0,
  coldHigh: 5,
  coldModerate: 12,
  heatModerate: 22,
  heatHigh: 27,
  heatSevere: 32,
}

/**
 * How much each vulnerability factor pulls the thresholds inward, in °C.
 *
 * A positive `cold` shift raises the cold cut-offs (so cold bites sooner);
 * a positive `heat` shift lowers the heat cut-offs (heat bites sooner).
 * Weights drive which advice leads.
 */
const FACTOR_SHIFTS: Record<
  string,
  { cold: number; heat: number; label: string; weight: number }
> = {
  over65: { cold: 2.5, heat: 2.5, label: 'Aged over 65', weight: 0.8 },
  over75: { cold: 4, heat: 4, label: 'Aged over 75', weight: 1.0 },
  youngChild: { cold: 2, heat: 3, label: 'Young child in the household', weight: 0.9 },
  pregnant: { cold: 1, heat: 2.5, label: 'Pregnancy', weight: 0.8 },
  respiratory: { cold: 3.5, heat: 1.5, label: 'Respiratory condition', weight: 0.9 },
  cardiovascular: { cold: 3, heat: 3, label: 'Heart or circulatory condition', weight: 0.95 },
  renal: { cold: 1, heat: 3, label: 'Kidney condition', weight: 0.9 },
  dementia: { cold: 2.5, heat: 3, label: 'Dementia or memory problems', weight: 0.95 },
  diabetes: { cold: 1.5, heat: 2, label: 'Diabetes', weight: 0.6 },
  mobility: { cold: 2, heat: 2, label: 'Reduced mobility', weight: 0.7 },
  medication: { cold: 1, heat: 2, label: 'Medication affecting temperature regulation', weight: 0.6 },
  coldHome: { cold: 3, heat: 0, label: 'Home is hard or costly to heat', weight: 0.85 },
  overheatingHome: { cold: 0, heat: 3, label: 'Home overheats (top floor or poor ventilation)', weight: 0.8 },
  outdoorWork: { cold: 2, heat: 2.5, label: 'Works or spends long periods outdoors', weight: 0.7 },
  livesAlone: { cold: 1, heat: 1, label: 'Lives alone', weight: 0.5 },
}

/**
 * Maximum threshold movement, in °C.
 *
 * Two separate caps, because vulnerability does not compress both ends of the
 * scale equally. Being frail barely changes the temperature at which you stop
 * feeling comfortable; it changes a lot how quickly that becomes dangerous.
 * So the comfort edge moves a little and the danger edges move more.
 *
 * The caps are also what keeps the bands monotonic. With
 * MAX_DANGER_SHIFT (4.5) < the 5°C baseline gap between heatModerate (22) and
 * heatHigh (27), the heat thresholds can never cross even for someone who
 * ticks every box. Same on the cold side against the 7°C gap. `assertOrdered`
 * below enforces this so a future edit to BASELINE cannot silently break it.
 */
const MAX_COMFORT_SHIFT = 4
const MAX_DANGER_SHIFT = 6

/**
 * Combine several factors with diminishing returns.
 *
 * Summing was wrong: being over 75 *and* having a heart condition *and* living
 * in a cold home does not make someone three times as cold-sensitive, and
 * summing drove the comfortable band shut. Take the largest factor at full
 * weight and add half of each remaining one.
 */
function compound(shifts: number[]): number {
  const sorted = shifts.filter((s) => s > 0).sort((a, b) => b - a)
  if (sorted.length === 0) return 0
  const [largest, ...rest] = sorted
  return largest + rest.reduce((sum, s) => sum + s, 0) * 0.5
}

/**
 * Squash a raw compounded shift into (0, max) along a saturating curve.
 *
 * A hard `Math.min` clip was worse than it looked: every persona's raw shift
 * exceeded the comfort cap, so all of them ended up with an identical
 * "comfortable range" while the UI claimed it was personalised. This curve
 * never reaches `max`, so two people with different factors always get
 * different numbers, and ordering is preserved for every possible input.
 *
 * HALF_AT is the raw shift that yields half of `max` — it sets how quickly the
 * curve flattens.
 */
const HALF_AT = 4
function soften(raw: number, max: number): number {
  if (raw <= 0) return 0
  return max * (raw / (raw + HALF_AT))
}

/** Build this person's adjusted thresholds. Exported so the UI can show them. */
/**
 * Medication as a graded shift rather than a flat one.
 *
 * The `medication` checkbox contributes { cold: 1, heat: 2 } whatever the person
 * is actually taking. Spec §8.2 weights the classes 1 to 3, with lithium heaviest
 * because dehydration concentrates it. Where the classes are known they replace
 * the flat figure; where they are not, the checkbox stands as before, so profiles
 * saved before the class picker existed still score.
 *
 * The heat side takes the burden directly and the cold side 40% of it — the
 * mechanisms in §8.3 (fluid loss, impaired sweating, blunted thirst, blunted
 * cutaneous blood flow) are overwhelmingly heat-side.
 */
const COLD_SHARE_OF_MEDICATION_RISK = 0.4

function medicationShift(profile: Profile): { cold: number; heat: number } | null {
  const burden = medicationBurden(profile.medClasses ?? [])
  if (burden <= 0) return null
  return { cold: burden * COLD_SHARE_OF_MEDICATION_RISK, heat: burden }
}

export function personalThresholds(profile: Profile): PersonalThresholds {
  const applicable = profile.factors
    .map((f) => FACTOR_SHIFTS[f])
    .filter((s): s is (typeof FACTOR_SHIFTS)[string] => Boolean(s))

  const graded = medicationShift(profile)
  const shifts = graded
    ? [...applicable.filter((s) => s.label !== FACTOR_SHIFTS.medication.label), graded]
    : applicable

  const coldRaw = compound(shifts.map((s) => s.cold))
  const heatRaw = compound(shifts.map((s) => s.heat))

  // Because soften() is bounded by its max, the gap between a danger shift and
  // its matching comfort shift is always under (MAX_DANGER - MAX_COMFORT) = 2,
  // comfortably inside the 5°C baseline gap. So the bands can never cross.
  const coldComfort = soften(coldRaw, MAX_COMFORT_SHIFT)
  const heatComfort = soften(heatRaw, MAX_COMFORT_SHIFT)
  const coldDanger = soften(coldRaw, MAX_DANGER_SHIFT)
  const heatDanger = soften(heatRaw, MAX_DANGER_SHIFT)

  const thresholds: PersonalThresholds = {
    coldSevere: BASELINE.coldSevere + coldDanger,
    coldHigh: BASELINE.coldHigh + coldDanger,
    coldModerate: BASELINE.coldModerate + coldComfort,
    heatModerate: BASELINE.heatModerate - heatComfort,
    heatHigh: BASELINE.heatHigh - heatDanger,
    heatSevere: BASELINE.heatSevere - heatDanger,
  }

  assertOrdered(thresholds)
  return thresholds
}

/**
 * Thresholds must be strictly increasing, or `bandFor` silently misclassifies
 * — which is exactly the bug this guards against: an inverted comfortable band
 * made it impossible for some profiles to ever read as comfortable.
 */
function assertOrdered(t: PersonalThresholds): void {
  const ordered = [t.coldSevere, t.coldHigh, t.coldModerate, t.heatModerate, t.heatHigh, t.heatSevere]
  for (let i = 1; i < ordered.length; i++) {
    if (ordered[i] <= ordered[i - 1]) {
      throw new Error(
        `Risk thresholds are not strictly increasing: ${JSON.stringify(t)}. ` +
          `Check MAX_COMFORT_SHIFT / MAX_DANGER_SHIFT against the BASELINE gaps.`,
      )
    }
  }
}

function bandFor(temp: number, t: PersonalThresholds): RiskBand {
  if (temp < t.coldSevere) return 'cold-severe'
  if (temp < t.coldHigh) return 'cold-high'
  if (temp < t.coldModerate) return 'cold-moderate'
  if (temp <= t.heatModerate) return 'comfortable'
  if (temp <= t.heatHigh) return 'heat-moderate'
  if (temp <= t.heatSevere) return 'heat-high'
  return 'heat-severe'
}

const BAND_ORDER: RiskBand[] = [
  'comfortable',
  'cold-moderate',
  'heat-moderate',
  'cold-high',
  'heat-high',
  'cold-severe',
  'heat-severe',
]

/** How serious a band is, ignoring direction. Higher = worse. */
export function bandRank(band: RiskBand): number {
  return BAND_ORDER.indexOf(band)
}

export function bandDirection(band: RiskBand): RiskDirection {
  if (band === 'comfortable') return 'none'
  return band.startsWith('cold') ? 'cold' : 'heat'
}

/** Human label for a band, for UI and for the assistant's context. */
export function bandLabel(band: RiskBand): string {
  const labels: Record<RiskBand, string> = {
    'cold-severe': 'Severe cold risk',
    'cold-high': 'High cold risk',
    'cold-moderate': 'Moderate cold risk',
    comfortable: 'Comfortable',
    'heat-moderate': 'Moderate heat risk',
    'heat-high': 'High heat risk',
    'heat-severe': 'Severe heat risk',
  }
  return labels[band]
}

function severityFor(temp: number, band: RiskBand, t: PersonalThresholds): number {
  // Map each band onto a 0-100 scale, interpolating within the band so two
  // people in the same band still order sensibly.
  const ramp = (value: number, from: number, to: number, lo: number, hi: number) => {
    const frac = Math.max(0, Math.min(1, (value - from) / (to - from)))
    return Math.round(lo + frac * (hi - lo))
  }

  switch (band) {
    case 'comfortable': {
      // Distance from the midpoint of the comfortable range.
      const mid = (t.coldModerate + t.heatModerate) / 2
      const halfWidth = (t.heatModerate - t.coldModerate) / 2 || 1
      return Math.round((Math.abs(temp - mid) / halfWidth) * 15)
    }
    case 'cold-moderate':
      return ramp(temp, t.coldModerate, t.coldHigh, 35, 16)
    case 'heat-moderate':
      return ramp(temp, t.heatModerate, t.heatHigh, 16, 35)
    case 'cold-high':
      return ramp(temp, t.coldHigh, t.coldSevere, 65, 36)
    case 'heat-high':
      return ramp(temp, t.heatHigh, t.heatSevere, 36, 65)
    case 'cold-severe':
      // 10°C below the severe cut-off is treated as the practical floor.
      return ramp(temp, t.coldSevere, t.coldSevere - 10, 66, 100)
    case 'heat-severe':
      return ramp(temp, t.heatSevere, t.heatSevere + 8, 66, 100)
  }
}

function driversFor(
  profile: Profile,
  weather: RegionWeather,
  direction: RiskDirection,
): RiskDriver[] {
  const drivers: RiskDriver[] = []

  for (const factor of profile.factors) {
    const shift = FACTOR_SHIFTS[factor]
    if (!shift) continue

    // Only surface a factor if it's relevant to the direction of risk. Being
    // over 75 matters in a cold snap and a heatwave, but "home overheats"
    // is noise in February.
    const relevant =
      direction === 'none' ||
      (direction === 'cold' && shift.cold > 0) ||
      (direction === 'heat' && shift.heat > 0)
    if (!relevant) continue

    drivers.push({ id: factor, label: shift.label, weight: shift.weight })
  }

  // Environmental drivers that come from the weather rather than the person.
  if (direction === 'cold' && weather.windSpeed >= 25) {
    drivers.push({
      id: 'windChill',
      label: `Wind chill — ${Math.round(weather.windSpeed)} km/h wind is making it feel ${Math.round(
        weather.temperature - weather.apparentTemperature,
      )}°C colder`,
      weight: 0.75,
    })
  }
  if (direction === 'heat' && weather.humidity >= 60) {
    drivers.push({
      id: 'humidity',
      label: `High humidity (${weather.humidity}%) — sweat evaporates poorly, so cooling is less effective`,
      weight: 0.7,
    })
  }
  if (direction === 'heat' && weather.todayApparentMin >= 20) {
    drivers.push({
      id: 'warmNight',
      label: `Tonight stays around ${Math.round(weather.todayApparentMin)}°C — little overnight recovery`,
      weight: 0.85,
    })
  }
  if (direction === 'cold' && weather.todayApparentMin <= 0) {
    drivers.push({
      id: 'freezingNight',
      label: `Dropping to about ${Math.round(weather.todayApparentMin)}°C overnight`,
      weight: 0.85,
    })
  }

  return drivers.sort((a, b) => b.weight - a.weight)
}

/**
 * The main entry point. Pure function — no I/O, no clock, no randomness, so
 * it is trivially testable and safe to run on the server or the client.
 */
export function assessRisk(profile: Profile, weather: RegionWeather): RiskAssessment {
  const thresholds = personalThresholds(profile)

  // Apparent temperature, not dry-bulb: wind chill and humidity are exactly
  // what makes a nominally mild day dangerous for a vulnerable person.
  const effectiveTemperature = weather.apparentTemperature

  const band = bandFor(effectiveTemperature, thresholds)
  const direction = bandDirection(band)
  const severity = severityFor(effectiveTemperature, band, thresholds)

  // Would today's forecast extreme land in a worse band than right now?
  const forecastBands: RiskBand[] = [
    bandFor(weather.todayApparentMax, thresholds),
    bandFor(weather.todayApparentMin, thresholds),
  ]
  const worseningToday = forecastBands.some((b) => bandRank(b) > bandRank(band))

  return {
    band,
    direction,
    severity,
    drivers: driversFor(profile, weather, direction),
    thresholds,
    headroomToNextBand: headroom(effectiveTemperature, band, thresholds),
    effectiveTemperature,
    worseningToday,
    weather,
    profileId: profile.id,
    interactions: matchingInteractions({
      conditions: profile.factors,
      medClasses: profile.medClasses ?? [],
      // The onboarding factors double as the person-level flags.
      flags: profile.factors,
      // No check-in has happened in this app yet, so the self-report rules
      // cannot fire. Passing nothing is deliberate: absent is not "no".
      selfReport: undefined,
      // The rules were written against dry-bulb peak and a modelled indoor
      // figure. This app has neither, so today's max stands in for peak air and
      // the apparent temperature for the indoor estimate. Both are honest
      // approximations; replacing them needs the FR-11 dwelling model, which is
      // noted as an open item in docs/reconciliation.md.
      peakAir: weather.todayMax,
      indoorDayEstimate: effectiveTemperature,
      tier: TIER_FOR_BAND[band],
    }),
  }
}

function headroom(temp: number, band: RiskBand, t: PersonalThresholds): number {
  // Distance to the boundary that would push this person into a worse band.
  const round = (n: number) => Math.round(n * 10) / 10
  switch (band) {
    case 'comfortable':
      return round(Math.min(temp - t.coldModerate, t.heatModerate - temp))
    case 'cold-moderate':
      return round(temp - t.coldHigh)
    case 'cold-high':
      return round(temp - t.coldSevere)
    case 'heat-moderate':
      return round(t.heatHigh - temp)
    case 'heat-high':
      return round(t.heatSevere - temp)
    default:
      return 0 // already in the worst band for that direction
  }
}

/**
 * Region-level banding for the map, using a healthy-adult baseline.
 *
 * The map shows the *place*, so it must not vary per viewer — a user's own
 * region is highlighted separately using their personal assessment.
 */
export function assessRegionBaseline(weather: RegionWeather): {
  band: RiskBand
  severity: number
} {
  const band = bandFor(weather.apparentTemperature, BASELINE)
  return {
    band,
    severity: severityFor(weather.apparentTemperature, band, BASELINE),
  }
}

/** Hex colour per band. Single source of truth shared by map and UI. */
export const BAND_COLOURS: Record<RiskBand, string> = {
  'cold-severe': '#2c5c8f',
  'cold-high': '#4e8fc4',
  'cold-moderate': '#8fc2de',
  comfortable: '#7fb069',
  'heat-moderate': '#f3c05a',
  'heat-high': '#e07a3f',
  'heat-severe': '#c1362f',
}
