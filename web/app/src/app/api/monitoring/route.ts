import { NextResponse } from 'next/server'

/**
 * The register scored across every day the forecast covers.
 *
 * The static panels on /monitoring argue from one day in the past. This is the
 * same argument made forwards, from live data — and it is the one a council can
 * act on, because it says who crosses into risk and how long there is to reach
 * them first.
 */

const CORE_URL = process.env.CORE_API_URL ?? 'http://127.0.0.1:8000'

export async function GET(request: Request) {
  // The heat episode is the default, matching the rest of the app: on a mild day
  // the live series is a flat row of zeros, which demonstrates nothing.
  const live = new URL(request.url).searchParams.get('scenario') === 'live'
  const response = await fetch(`${CORE_URL}/monitoring/forecast${live ? '' : '?scenario=heat'}`, {
    cache: 'no-store',
  }).catch(() => null)

  if (!response?.ok) {
    // The historical panels stand on their own, so a missing forecast should
    // degrade this section rather than break the page.
    return NextResponse.json({ unavailable: true, days: [], first_at_risk: [] })
  }
  return NextResponse.json(await response.json())
}
