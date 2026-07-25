import { NextResponse } from 'next/server'

import { getAdvice } from '@/lib/advice'
import { DEMO_PROFILES, isValidProfile, type Profile } from '@/lib/profile'
import { regionByCode } from '@/lib/regions'
import { assessRisk, bandLabel } from '@/lib/risk'
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
  const snapshot = await fetchAllRegions()

  return profiles.map((profile) => {
    let weather = snapshot.regions.find((r) => r.regionCode === profile.regionCode)
    if (!weather) {
      return { profile: profile.name, error: `No weather for region ${profile.regionCode}` }
    }

    // What-if override: substitute a feels-like temperature to answer "what
    // will this person be told when it reaches 30°C?" Real conditions are
    // still used for humidity, wind and today's range.
    if (atTemperature !== undefined) {
      weather = { ...weather, apparentTemperature: atTemperature }
    }

    const assessment = assessRisk(profile, weather)

    return {
      profile: {
        id: profile.id,
        name: profile.name,
        region: regionByCode(profile.regionCode)?.name,
        factors: profile.factors,
      },
      conditions: {
        temperature: weather.temperature,
        apparentTemperature: weather.apparentTemperature,
        conditions: describeWeatherCode(weather.weatherCode),
        todayMin: weather.todayMin,
        todayMax: weather.todayMax,
      },
      assessment: {
        band: assessment.band,
        bandLabel: bandLabel(assessment.band),
        direction: assessment.direction,
        severity: assessment.severity,
        thresholds: assessment.thresholds,
        headroomToNextBand: assessment.headroomToNextBand,
        worseningToday: assessment.worseningToday,
        drivers: assessment.drivers,
      },
      advice: getAdvice(assessment),
    }
  })
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
