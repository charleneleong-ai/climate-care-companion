import { NextResponse } from 'next/server'

/**
 * Registering a device for alerts.
 *
 * A thin proxy. The subscription is stored by the Python service because that is
 * what the three-hourly sweep reads — a copy held in the Next.js process would
 * be the wrong one within a restart.
 *
 * POST   { subscription, personId, audience }  → register
 * DELETE { endpoint }                          → unregister
 */

const CORE_URL = process.env.CORE_API_URL ?? 'http://127.0.0.1:8000'

/**
 * Forward to the core, preserving why it said no.
 *
 * An unreachable service and a rejected registration need different words: the
 * first is worth retrying, the second never will be. Collapsing both into "could
 * not reach" sends someone to check their signal over a bad person id.
 */
async function forward(method: 'POST' | 'DELETE', body: unknown) {
  const response = await fetch(`${CORE_URL}/push/subscribe`, {
    method,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).catch(() => null)

  if (!response) {
    return NextResponse.json({ error: 'could not reach the alert service' }, { status: 502 })
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    return NextResponse.json(
      { error: payload.detail ?? 'the alert service refused this registration' },
      { status: response.status },
    )
  }
  return NextResponse.json(payload)
}

export async function POST(request: Request) {
  // `json()` throws on a malformed or empty body, so without this the handler
  // 500s before reaching the 400 it carefully constructs two lines below.
  const body = await request.json().catch(() => null)
  const { subscription, personId, audience } = body ?? {}

  if (!subscription?.endpoint || !subscription?.keys?.p256dh || !subscription?.keys?.auth) {
    return NextResponse.json({ error: 'incomplete push subscription' }, { status: 400 })
  }
  if (!personId || !audience) {
    // Without both, a push has no one to be about and no voice to be written in.
    return NextResponse.json({ error: 'personId and audience are required' }, { status: 400 })
  }

  return forward('POST', {
    endpoint: subscription.endpoint,
    p256dh: subscription.keys.p256dh,
    auth: subscription.keys.auth,
    person_id: personId,
    audience,
  })
}

export async function DELETE(request: Request) {
  const { endpoint } = (await request.json().catch(() => null)) ?? {}
  if (!endpoint) {
    return NextResponse.json({ error: 'endpoint is required' }, { status: 400 })
  }

  return forward('DELETE', { endpoint })
}
