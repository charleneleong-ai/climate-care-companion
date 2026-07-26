import { NextResponse } from 'next/server'

/**
 * One person's tier across the days.
 *
 * The companion screen answers "is it safe tonight?" — the right first question,
 * but it hides the shape. Someone Low today and High on Saturday needs telling
 * on Thursday, and a caregiver who only ever sees tonight cannot plan around it.
 */

const CORE_URL = process.env.CORE_API_URL ?? 'http://127.0.0.1:8000'

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const live = new URL(request.url).searchParams.get('scenario') === 'live'

  const response = await fetch(
    `${CORE_URL}/people/${encodeURIComponent(id)}/series${live ? '' : '?scenario=heat'}`,
    { cache: 'no-store' },
  ).catch(() => null)

  if (!response?.ok) {
    // Tonight's assessment stands on its own, so a missing series should quietly
    // drop this strip rather than break the screen someone opened to act on.
    return NextResponse.json({ points: [], unavailable: true })
  }
  return NextResponse.json(await response.json())
}
