import { NextResponse } from 'next/server'

import { ALL_FACTOR_IDS, isValidProfile, outwardCode } from '@/lib/profile'
import { getProfileStore } from '@/lib/profile-store'
import { regionByCode } from '@/lib/regions'

/**
 * GET  /api/profiles  → the roster (demo personas + anyone onboarded)
 * POST /api/profiles  → register a profile from onboarding
 *
 * Registration is not authentication. The client keeps its own copy in
 * localStorage; this exists so the demo can show several real people using the
 * app at once, and so a future durable store has an obvious place to live.
 */

export async function GET() {
  const profiles = await getProfileStore().list()
  return NextResponse.json({ profiles }, { headers: { 'Cache-Control': 'no-store' } })
}

export async function POST(request: Request) {
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 })
  }

  if (!isValidProfile(body)) {
    return NextResponse.json(
      { error: 'A profile needs at least an id, a name, a regionCode and a factors array.' },
      { status: 400 },
    )
  }

  if (!regionByCode(body.regionCode)) {
    return NextResponse.json(
      { error: `Unknown region code "${body.regionCode}".` },
      { status: 422 },
    )
  }

  const unknownFactors = body.factors.filter((f) => !ALL_FACTOR_IDS.includes(f))
  if (unknownFactors.length > 0) {
    return NextResponse.json(
      { error: `Unknown factors: ${unknownFactors.join(', ')}` },
      { status: 422 },
    )
  }

  // Normalise before storing: trim the name, and keep only the outward code
  // even if a client sent a full postcode.
  const stored = await getProfileStore().save({
    ...body,
    name: body.name.trim().slice(0, 60),
    postcodeOutward: body.postcodeOutward ? outwardCode(body.postcodeOutward) : undefined,
    notes: body.notes?.trim().slice(0, 500) || undefined,
    createdAt: body.createdAt || new Date().toISOString(),
  })

  return NextResponse.json({ profile: stored }, { status: 201 })
}
