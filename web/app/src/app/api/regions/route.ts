import { NextResponse } from 'next/server'

import { assessRegionBaseline } from '@/lib/risk'
import { describeWeatherCode, fetchAllRegions } from '@/lib/weather'

/**
 * GET /api/regions
 *
 * Current conditions + baseline risk band for all 12 UK regions. Powers the
 * map choropleth. Baseline (healthy-adult) banding, not per-user — the map
 * shows the place, so it must look the same to everyone.
 */
export async function GET() {
  try {
    const snapshot = await fetchAllRegions()

    return NextResponse.json(
      {
        fetchedAt: snapshot.fetchedAt,
        regions: snapshot.regions.map((weather) => ({
          ...weather,
          conditions: describeWeatherCode(weather.weatherCode),
          ...assessRegionBaseline(weather),
        })),
      },
      {
        headers: {
          // Matches the 10-minute upstream cache in weather.ts.
          'Cache-Control': 'public, s-maxage=600, stale-while-revalidate=300',
        },
      },
    )
  } catch (error) {
    console.error('[api/regions] failed to fetch weather', error)
    return NextResponse.json(
      { error: 'Could not reach the weather service. Try again shortly.' },
      { status: 502 },
    )
  }
}
