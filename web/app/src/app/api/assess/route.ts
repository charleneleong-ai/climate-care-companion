import { NextResponse } from 'next/server'

import { DEMO_PROFILES, isValidProfile, type Profile } from '@/lib/profile'
import { regionByCode } from '@/lib/regions'
import { assessViaCore } from '@/lib/assess-client'
import { bandForTier, bandLabel, directionForCodes } from '@/lib/risk'
import { describeWeatherCode, fetchAllRegions } from '@/lib/weather'

/**
 * Risk + advice for a profile against live weather.
 *
 * GET  /api/assess              → all five demo personas (quickest way to see
 *                                 the same weather produce different advice)
 * GET  /api/assess?id=demo-doris → one demo persona
 * POST /api/assess  { profile }  → any profile
 *
 * Useful to whoever is writing the advice content: edit lib/advice.ts, curl
 * this, see the result. No UI, no onboarding, no map.
 */

async function assessProfiles(profiles: Profile[], atTemperature?: number) {
  const snapshot = await fetchAllRegions().catch(() => null)

  return Promise.all(
    profiles.map(async (profile) => {
      const weather = snapshot?.regions.find((r) => r.regionCode === profile.regionCode)

      let core
      try {
        core = await assessViaCore(profile)
      } catch (error) {
        // The core being unreachable is a fact to report, not an exception to
        // swallow. A caregiver told "no assessment available" can act on that;
        // one shown a fabricated tier cannot.
        return {
          profile: profile.name,
          error: `Risk core unavailable: ${(error as Error).message}`,
        }
      }

      const direction = directionForCodes(core.reasons.map((r) => r.code))
      const band = bandForTier(core.tier, direction)

      return {
        profile: {
          id: profile.id,
          name: profile.name,
          region: regionByCode(profile.regionCode)?.name,
          factors: profile.factors,
          medClasses: profile.medClasses ?? [],
        },
        conditions: weather
          ? {
              temperature: weather.temperature,
              apparentTemperature: weather.apparentTemperature,
              conditions: describeWeatherCode(weather.weatherCode),
              todayMin: weather.todayMin,
              todayMax: weather.todayMax,
              /** Display only. The core fetches its own hourly forecast, because
               *  FR-07's overnight minimum needs the 22:00–07:00 window and a
               *  daily minimum cannot answer it. */
              note: atTemperature !== undefined ? 'what-if not supported by the core' : undefined,
            }
          : null,
        assessment: {
          tier: core.tier,
          band,
          bandLabel: bandLabel(band),
          direction,
          riskScore: core.risk_score,
          exposureScore: core.exposure_score,
          vulnerabilityScore: core.vulnerability_score,
          // SC-5: the label is in the key, so no caller can drop it.
          indoorNightEstimateModelled: core.exposure.indoor_night_est_modelled,
          indoorDayEstimateModelled: core.exposure.indoor_day_est_modelled,
          /** live | cache. A stale figure must never read as a fresh one. */
          source: core.exposure.source,
          reasons: core.reasons,
        },
        /** Advice comes from the core too. It holds the interaction rules and
         *  the SC-1 gate; generating it here would be a second opinion. */
        plan: core.plan,
      }
    }),
  )
}

/** Parse the optional `at` what-if temperature, rejecting nonsense values. */
function parseAt(raw: string | null): { value?: number; error?: string } {
  if (raw === null) return {}
  const value = Number(raw)
  if (!Number.isFinite(value)) return { error: `"at" must be a number, got "${raw}".` }
  if (value < -30 || value > 55) return { error: '"at" must be between -30 and 55 °C.' }
  return { value }
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams
  const id = params.get('id')

  const at = parseAt(params.get('at'))
  if (at.error) return NextResponse.json({ error: at.error }, { status: 400 })

  const profiles = id ? DEMO_PROFILES.filter((p) => p.id === id) : DEMO_PROFILES

  if (profiles.length === 0) {
    return NextResponse.json(
      { error: `No demo profile "${id}". Try one of: ${DEMO_PROFILES.map((p) => p.id).join(', ')}` },
      { status: 404 },
    )
  }

  try {
    return NextResponse.json(
      { atTemperature: at.value ?? null, results: await assessProfiles(profiles, at.value) },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  } catch (error) {
    console.error('[api/assess] failed', error)
    return NextResponse.json({ error: 'Could not reach the weather service.' }, { status: 502 })
  }
}

export async function POST(request: Request) {
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 })
  }

  const profile = (body as { profile?: unknown })?.profile ?? body

  if (!isValidProfile(profile)) {
    return NextResponse.json(
      { error: 'Send a valid profile, either as the body or as { "profile": ... }.' },
      { status: 400 },
    )
  }

  try {
    const [result] = await assessProfiles([profile])
    return NextResponse.json(result, { headers: { 'Cache-Control': 'no-store' } })
  } catch (error) {
    console.error('[api/assess] failed', error)
    return NextResponse.json({ error: 'Could not reach the weather service.' }, { status: 502 })
  }
}
