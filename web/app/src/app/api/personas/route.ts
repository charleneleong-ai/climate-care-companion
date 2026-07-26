import { NextResponse } from 'next/server'

/**
 * The seeded personas, for signing in as one during a demo.
 *
 * They live in the Python service as YAML — a persona carries a dwelling, a
 * medication list and an age band that the web `Profile` shape has nowhere to
 * put. Rather than flatten them into a Profile and lose the detail that makes
 * the advice specific, this proxies the core and the companion screen reads the
 * core's answer directly.
 */

const CORE_URL = process.env.CORE_API_URL ?? 'http://127.0.0.1:8000'

const AGE_LABEL: Record<string, string> = {
  under_65: 'Under 65',
  b65_74: '65 to 74',
  b75_84: '75 to 84',
  b85_plus: '85 and over',
}

export async function GET() {
  const response = await fetch(`${CORE_URL}/people`, { cache: 'no-store' }).catch(() => null)
  if (!response?.ok) {
    return NextResponse.json({ error: 'The risk service is unavailable.' }, { status: 502 })
  }

  const people = (await response.json()) as { id: string; name: string; age_band: string }[]
  return NextResponse.json({
    people: people.map((p) => ({
      id: p.id,
      name: p.name,
      ageBand: p.age_band,
      ageLabel: AGE_LABEL[p.age_band] ?? p.age_band,
    })),
  })
}
