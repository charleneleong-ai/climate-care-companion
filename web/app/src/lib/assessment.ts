'use client'

/**
 * The core's assessment, and the one way of asking for it.
 *
 * Everything that shows a tier goes through here. The alternative — each view
 * scoring for itself — is what put the assistant and the advice panel side by
 * side describing different days, and `/` and `/companion` on different
 * engines. There is one risk model and it is in `packages/core`; this is the
 * client half of the wire to it.
 */

import { useEffect, useState } from 'react'

import type { Audience } from './assess-client'
import type { Profile } from './profile'
import type { RiskBand } from './risk'

export type Tier = 'Low' | 'Elevated' | 'High' | 'Severe'

export interface Reason {
  code: string
  title: string
  explanation: string
  weight: number
}

export interface PlanItem {
  code: string
  text: string
  watch_for: string | null
  escalate_to: string | null
  source: 'interaction' | 'reason_code' | 'self_report'
}

export interface AssessmentResult {
  profile: { name: string }
  assessment: {
    tier: Tier
    band: RiskBand
    bandLabel: string
    direction: 'heat' | 'cold' | 'none'
    riskScore: number
    exposureScore: number
    vulnerabilityScore: number
    indoorNightEstimateModelled: number
    source: string
    reasons: Reason[]
  }
  plan: {
    items: PlanItem[]
    watch_points: string[]
    escalate_to: string[]
  }
  error?: string
}

/** What the tier means in terms of when to act. Shared so `/` and `/companion`
 *  cannot describe the same tier differently.
 *
 *  Two voices, because the plan the core returns has two and this line sits
 *  directly above it. "Do not leave them alone overnight" shown to the person
 *  it is about is not a softer version of the same sentence — it is addressed
 *  to someone who is not reading it. */
export const TIER: Record<
  Tier,
  { shape: string; tone: string; act: Record<Audience, string> }
> = {
  Low: {
    shape: 'circle',
    tone: 'low',
    act: { caregiver: 'No action beyond routine.', cared_for: 'Nothing extra to do today.' },
  },
  Elevated: {
    shape: 'square',
    tone: 'elevated',
    act: { caregiver: 'Check in today.', cared_for: 'Worth taking care today.' },
  },
  High: {
    shape: 'triangle',
    tone: 'high',
    act: {
      caregiver: 'Act before this evening.',
      cared_for: 'Do something about this before this evening.',
    },
  },
  Severe: {
    shape: 'diamond',
    tone: 'severe',
    act: {
      caregiver: 'Act now. Do not leave them alone overnight.',
      cared_for: 'Act now, and do not spend tonight alone.',
    },
  },
}

export const SOURCE_LABEL: Record<PlanItem['source'], string> = {
  interaction: 'combination',
  self_report: 'they told us',
  reason_code: '',
}

export const ESCALATION: Record<string, string> = {
  gp: 'Ring the GP',
  pharmacist: 'Ask the pharmacist',
  council: 'Council welfare',
}

// Versioned, so a payload written by an older shape is ignored rather than
// cast to the current one and dereferenced during render.
const CACHE_KEY = 'climatise:assessment:v2'

/** Per person, per scenario, per audience — every axis that changes the answer.
 *  Keying on scenario alone meant switching profile showed the previous
 *  person's reasons and plan under the new person's name. */
function cacheKeyFor(profile: Profile, scenario: boolean, audience: Audience): string {
  return `${CACHE_KEY}:${profile.id}:${scenario ? 'heat' : 'live'}:${audience}`
}

/** A cached payload is untrusted input — it outlives the code that wrote it. */
function isUsable(value: unknown): value is AssessmentResult {
  const result = value as AssessmentResult | null
  return (
    !!result &&
    typeof result.assessment?.tier === 'string' &&
    typeof result.assessment?.indoorNightEstimateModelled === 'number' &&
    Array.isArray(result.assessment?.reasons) &&
    Array.isArray(result.plan?.items)
  )
}

export interface AssessmentState {
  result: AssessmentResult | null
  /** Showing a cached answer because the live one has not arrived or failed.
   *  NFR-04 wants the last assessment served offline — but never dressed up as
   *  a fresh one. */
  stale: boolean
  failed: boolean
}

export function useCoreAssessment(
  profile: Profile | null,
  heatScenario: boolean,
  audience: Audience = 'caregiver',
): AssessmentState {
  const [result, setResult] = useState<AssessmentResult | null>(null)
  const [stale, setStale] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!profile) return
    // Nothing on screen may outlive the person it describes, so the previous
    // answer is dropped before the new one is asked for.
    setResult(null)
    setStale(false)
    setFailed(false)

    // Toggling the scenario twice quickly must not let the slower reply win and
    // paint the wrong day.
    let current = true
    const key = cacheKeyFor(profile, heatScenario, audience)

    const cached = typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null
    if (cached) {
      try {
        const parsed: unknown = JSON.parse(cached)
        if (isUsable(parsed)) {
          setResult(parsed)
          setStale(true)
        }
      } catch {
        /* corrupt cache */
      }
    }

    const query = new URLSearchParams({ audience })
    if (heatScenario) query.set('demo', 'heat')

    void (async () => {
      try {
        const response = await fetch(`/api/assess?${query}`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ profile }),
        })
        if (!response.ok) throw new Error(String(response.status))
        const body = (await response.json()) as AssessmentResult
        if (body.error) throw new Error(body.error)
        if (!current) return
        setResult(body)
        setStale(false)
        setFailed(false)
        localStorage.setItem(key, JSON.stringify(body))
      } catch {
        if (current) setFailed(true)
      }
    })()

    return () => {
      current = false
    }
  }, [profile, heatScenario, audience])

  return { result, stale, failed }
}
