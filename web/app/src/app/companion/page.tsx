'use client'

/**
 * The companion screen.
 *
 * Add ?demo=heat to the URL to show the Bedford 19 July 2025 heatwave scenario
 * instead of live weather. A banner explains the date, what happened, and why
 * it was missed by the national alert system. Toggling between live and the
 * scenario is the demo's core move: same person, same profile, different risk.
 *
 * What a caregiver opens at nine at night to find out whether the person they
 * look after is safe. Scored by the Python core — this renders, it does not
 * decide.
 *
 * Three constraints shape the layout rather than decorate it:
 *   NFR-06  body text at or above 16px, tap targets at or above 44px
 *   NFR-07  a tier is never colour alone — shape and word carry it too
 *   SC-5    modelled values say they are modelled, everywhere they appear
 */

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { loadProfile } from '@/lib/client-store'
import type { Profile } from '@/lib/profile'

type Tier = 'Low' | 'Elevated' | 'High' | 'Severe'

interface Reason {
  code: string
  title: string
  explanation: string
  weight: number
}

interface PlanItem {
  code: string
  text: string
  watch_for: string | null
  escalate_to: string | null
  source: 'interaction' | 'reason_code' | 'self_report'
}

interface Result {
  profile: { name: string }
  assessment: {
    tier: Tier
    bandLabel: string
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

const TIER: Record<Tier, { shape: string; tone: string; act: string }> = {
  Low: { shape: 'circle', tone: 'low', act: 'No action beyond routine.' },
  Elevated: { shape: 'square', tone: 'elevated', act: 'Check in today.' },
  High: { shape: 'triangle', tone: 'high', act: 'Act before this evening.' },
  Severe: {
    shape: 'diamond',
    tone: 'severe',
    act: 'Act now. Do not leave them alone overnight.',
  },
}

const SOURCE_LABEL: Record<PlanItem['source'], string> = {
  interaction: 'combination',
  self_report: 'they told us',
  reason_code: '',
}

const ESCALATION: Record<string, string> = {
  gp: 'Ring the GP',
  pharmacist: 'Ask the pharmacist',
  council: 'Council welfare',
}

const CACHE_KEY = 'climatise:last-assessment'

export default function CompanionPage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [stale, setStale] = useState(false)
  const [failed, setFailed] = useState(false)
  const [audience, setAudience] = useState<'caregiver' | 'cared_for'>('caregiver')
  // Heatwave scenario is the default — it is the demo's point.
  // ?demo=live in the URL switches to live weather instead.
  const [heatScenario, setHeatScenario] = useState(true)

  useEffect(() => {
    setProfile(loadProfile())
    // ?demo=live overrides the default to show current conditions.
    if (typeof window !== 'undefined') {
      const demo = new URLSearchParams(window.location.search).get('demo')
      if (demo === 'live') setHeatScenario(false)
    }
  }, [])

  const load = useCallback(async (p: Profile, scenario: boolean) => {
    // NFR-04: show the last answer straight away rather than a spinner. A
    // caregiver on a bad connection gets something they can act on, labelled
    // as stale, instead of nothing.
    const cacheKey = scenario ? `${CACHE_KEY}:heat` : CACHE_KEY
    const cached = typeof localStorage !== 'undefined' ? localStorage.getItem(cacheKey) : null
    if (cached) {
      try {
        setResult(JSON.parse(cached) as Result)
        setStale(true)
      } catch {
        /* a corrupt cache is not worth reporting — it is about to be replaced */
      }
    }

    try {
      const url = scenario ? '/api/assess?demo=heat' : '/api/assess'
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ profile: p }),
      })
      if (!response.ok) throw new Error(String(response.status))
      const body = (await response.json()) as Result
      if (body.error) throw new Error(body.error)

      setResult(body)
      setStale(false)
      setFailed(false)
      localStorage.setItem(cacheKey, JSON.stringify(body))
    } catch {
      setFailed(true)
    }
  }, [])

  useEffect(() => {
    if (profile) void load(profile, heatScenario)
  }, [profile, load, heatScenario])

  if (!profile) {
    return (
      <main className="mx-auto max-w-[30rem] px-5 py-10">
        <h1 className="text-xl font-semibold">No one set up yet</h1>
        <p className="mt-2 text-[16px] muted">
          Tell us about the person you look after and we can tell you whether tonight is
          safe for them.
        </p>
        <Link href="/onboarding" className="btn btn-primary mt-6 inline-flex">
          Set up
        </Link>
      </main>
    )
  }

  if (!result) {
    return (
      <main className="mx-auto max-w-[30rem] px-5 py-10">
        <p className="text-[16px] muted">
          {failed ? 'Cannot reach the risk service, and nothing is saved yet.' : 'Checking…'}
        </p>
      </main>
    )
  }

  const a = result.assessment
  const tier = TIER[a.tier]
  const plan = result.plan
  const visible = audience === 'caregiver' ? plan.items : plan.items.filter((i) => i.text)

  return (
    <main className="mx-auto max-w-[30rem] px-5 pb-24 pt-8">
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] faint">
        Climatise · companion
      </p>
      <h1 className="mt-1.5 text-[21px] font-semibold tracking-tight">
        Is it safe for {result.profile.name} tonight?
      </h1>

      {/* Heatwave scenario banner — explains the historic date and the
          national alerting gap this system exists to close. */}
      <div
        className="mt-4 overflow-hidden rounded-[var(--radius-lg)] border"
        style={{
          borderColor: heatScenario ? '#d97706' : 'var(--line)',
          background: heatScenario ? '#fffbeb' : 'var(--surface)',
        }}
      >
        <div className="flex items-start justify-between gap-3 p-3.5">
          <div className="min-w-0">
            {heatScenario ? (
              <>
                <p className="text-[13px] font-semibold" style={{ color: '#92400e' }}>
                  Showing: 19 July 2025 · Bedford
                </p>
                <p className="mt-0.5 text-[12.5px]" style={{ color: '#78350f' }}>
                  No heat-health alert was issued that day. An estimated 146 people
                  died. This is what the system would have shown.
                </p>
              </>
            ) : (
              <p className="text-[13px] faint">
                Showing live weather today.
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => setHeatScenario((v) => !v)}
            className="btn btn-ghost shrink-0 px-3 py-1.5 text-[13px]"
            style={{ minHeight: 'auto', color: heatScenario ? '#92400e' : undefined }}
          >
            {heatScenario ? 'Show live' : '19 Jul 2025'}
          </button>
        </div>
      </div>

      {(stale || failed) && (
        <p
          role="status"
          className="mt-3 rounded-lg border px-3.5 py-2.5 text-[14px]"
          style={{ borderColor: 'var(--warn-line, #d9a441)', color: 'var(--warn-ink, #8a5a12)' }}
        >
          Showing the last saved check. {failed ? 'No connection.' : 'Updating…'}
        </p>
      )}

      {/* NFR-07: shape, word and colour together. */}
      <section className={`card mt-5 p-5 tone-${tier.tone}`}>
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className={`glyph glyph-${tier.shape}`} />
          <span className="text-[22px] font-bold tracking-tight">{a.tier}</span>
        </div>
        <p className="mt-2.5 text-[15px] muted">{tier.act}</p>

        <dl className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-lg">
          {[
            ['exposure', a.exposureScore],
            ['vulnerability', a.vulnerabilityScore],
            ['risk score', a.riskScore.toFixed(1)],
          ].map(([label, value]) => (
            <div key={label as string} className="bg-[var(--panel-2)] px-3 py-2.5">
              <dd className="font-mono text-[16px] tabular-nums">{value}</dd>
              <dt className="mt-0.5 text-[11px] faint">{label}</dt>
            </div>
          ))}
        </dl>

        <p className="mt-3 text-[12.5px] faint">
          Bedroom tonight, <span title="Estimated from the forecast and their home, not measured" className="underline decoration-dotted">modelled</span>{' '}
          at {a.indoorNightEstimateModelled}°C · forecast {a.source}
        </p>
      </section>

      <Section title="Why">
        {a.reasons.map((r) => (
          <div key={r.code} className="row">
            <span className="float-right font-mono text-[11px] tabular-nums faint">+{r.weight}</span>
            <p className="text-[15px] font-semibold">{r.title}</p>
            <p className="mt-1 text-[13.5px] muted">{r.explanation}</p>
          </div>
        ))}
      </Section>

      <section className="mt-6">
        <h2 className="section-label">What to do before tonight</h2>
        <div className="switch" role="group" aria-label="Who the advice is written for">
          {(['caregiver', 'cared_for'] as const).map((who) => (
            <button
              key={who}
              type="button"
              aria-pressed={audience === who}
              onClick={() => setAudience(who)}
            >
              {who === 'caregiver' ? 'For you' : `For ${result.profile.name}`}
            </button>
          ))}
        </div>

        <div className="card mt-2.5">
          {visible.length === 0 ? (
            <p className="p-4 text-[14px] faint">
              Nothing here is written for {result.profile.name} to act on. Advice they
              cannot act on themselves is addressed to you instead.
            </p>
          ) : (
            visible.map((item) => (
              <div key={item.code} className="row">
                {SOURCE_LABEL[item.source] && (
                  <p className="mb-1.5">
                    <span className={`tag tag-${item.source}`}>{SOURCE_LABEL[item.source]}</span>
                  </p>
                )}
                <p className="text-[15px]">{item.text}</p>
              </div>
            ))
          )}
        </div>

        {plan.escalate_to.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-2">
            {plan.escalate_to.map((who, i) => (
              <span key={who} className={`btn ${i === 0 ? 'btn-primary' : 'btn-secondary'}`}>
                {ESCALATION[who] ?? who}
              </span>
            ))}
          </div>
        )}
      </section>

      {audience === 'caregiver' && plan.watch_points.length > 0 && (
        <Section title="What to watch for">
          {plan.watch_points.map((point) => (
            <p key={point} className="row text-[14px] muted">
              {point}
            </p>
          ))}
        </Section>
      )}

      <p className="mt-8 text-[12px] faint">
        <strong>Demonstrator only.</strong> Not medical advice and not clinically
        validated. Never change a prescribed medicine on the basis of this app — speak
        to a pharmacist or GP.
      </p>
    </main>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="section-label">{title}</h2>
      <div className="card">{children}</div>
    </section>
  )
}
