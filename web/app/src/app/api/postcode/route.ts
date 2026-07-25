import { NextResponse } from 'next/server'

import { regionFromPostcodeLookup } from '@/lib/regions'

/**
 * GET /api/postcode?q=SW1A1AA
 *
 * Resolve a UK postcode to one of the 12 ITL1 regions via postcodes.io
 * (free, no key). Proxied server-side so onboarding works even where the
 * client is behind a restrictive network, and so we never store the full
 * postcode — only the region comes back.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const raw = searchParams.get('q')?.trim()

  if (!raw) {
    return NextResponse.json({ error: 'Provide a postcode as ?q=' }, { status: 400 })
  }

  // Cheap shape check before spending a network call. Deliberately loose —
  // postcodes.io is the real validator.
  if (!/^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$/.test(raw)) {
    return NextResponse.json(
      { error: 'That does not look like a full UK postcode.' },
      { status: 400 },
    )
  }

  try {
    const res = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(raw)}`, {
      next: { revalidate: 86400 }, // postcode → region effectively never changes
    })

    if (res.status === 404) {
      return NextResponse.json({ error: 'Postcode not found.' }, { status: 404 })
    }
    if (!res.ok) {
      throw new Error(`postcodes.io returned ${res.status}`)
    }

    const body = await res.json()
    const region = regionFromPostcodeLookup(body.result)

    if (!region) {
      return NextResponse.json(
        { error: 'Could not match that postcode to a UK region.' },
        { status: 422 },
      )
    }

    return NextResponse.json({
      regionCode: region.code,
      regionName: region.name,
      // The outward code is all we hand back — enough to show the user we got
      // it right, without the app ever holding a full address.
      outwardCode: body.result.outcode as string,
      adminDistrict: body.result.admin_district as string | null,
    })
  } catch (error) {
    console.error('[api/postcode] lookup failed', error)
    return NextResponse.json({ error: 'Postcode lookup is unavailable.' }, { status: 502 })
  }
}
