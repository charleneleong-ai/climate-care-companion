import { NextResponse } from 'next/server'

/**
 * One persona's live assessment and plan, in the shape the companion screen
 * already renders — so signing in as a persona lands on exactly the screen a
 * real sign-up does, rather than a separate demo view that could drift from it.
 *
 * The weather is live. Only the person is seeded.
 */

const CORE_URL = process.env.CORE_API_URL ?? 'http://127.0.0.1:8000'

const BAND_LABEL: Record<string, string> = {
  Low: 'No action beyond routine',
  Elevated: 'Worth a check today',
  High: 'Act before this evening',
  Severe: 'Act now',
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const query = new URL(request.url).searchParams
  const audience = query.get('audience') ?? 'caregiver'
  // Same scenario switch the assess route uses, so a persona and a real sign-up
  // are never showing two different days.
  const fixture = query.get('demo') === 'heat' ? '&fixture=heat' : ''

  const response = await fetch(
    `${CORE_URL}/people/${encodeURIComponent(id)}/assessment?audience=${audience}${fixture}`,
    { cache: 'no-store' },
  ).catch(() => null)

  if (!response) {
    return NextResponse.json({ error: 'The risk service is unavailable.' }, { status: 502 })
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    return NextResponse.json(
      { error: body.detail ?? 'That person could not be assessed.' },
      { status: response.status },
    )
  }

  const core = await response.json()
  return NextResponse.json({
    profile: { name: core.name },
    assessment: {
      tier: core.tier,
      bandLabel: BAND_LABEL[core.tier] ?? core.tier,
      riskScore: core.risk_score,
      exposureScore: core.exposure_score,
      vulnerabilityScore: core.vulnerability_score,
      indoorNightEstimateModelled: core.exposure.indoor_night_est_modelled,
      source: core.exposure.source,
      reasons: core.reasons,
    },
    plan: core.plan,
  })
}
