import { NextResponse } from 'next/server'

/**
 * A person's check-in history, for the companion screen.
 *
 * Read from the voice service rather than the risk core: the core decides what
 * the weather means, the check-in service records what the person said. Keeping
 * them apart is what lets a self-report contradict an estimate — which is the
 * whole reason for asking.
 */

const VOICE_URL = process.env.VOICE_API_URL ?? 'http://127.0.0.1:8001'

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params

  const response = await fetch(`${VOICE_URL}/checkins/${encodeURIComponent(id)}`, {
    cache: 'no-store',
  }).catch(() => null)

  if (!response?.ok) {
    // Not an error worth blocking the screen for — the assessment stands on its
    // own, and "no check-in history" is indistinguishable from "service down"
    // to a reader who only wants tonight's advice.
    return NextResponse.json({ person_id: id, count: 0, checkins: [], unavailable: true })
  }
  return NextResponse.json(await response.json())
}
