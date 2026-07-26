'use client'

/**
 * Shared assessment view used by /personal and /caregiver.
 *
 * The only difference between the two routes is the default audience and
 * the framing copy. Everything else — heatwave scenario, tier badge, reasons,
 * plan, watch-fors — is identical.
 *
 * The heatwave banner shows the actual conditions from 19 July 2025 as if
 * you are looking at the dashboard on that day: temperature, alert status,
 * overnight forecast, day of the spell.
 */

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { loadProfile } from '@/lib/client-store'
import type { Profile } from '@/lib/profile'

type Tier = 'Low' | 'Elevated' | 'High' | 'Severe'
type Audience = 'caregiver' | 'cared_for'

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

// 19 July 2025 conditions — Bedford, no regional alert.
const HEAT_FIXTURE_CONTEXT = {
  date: 'Saturday 19 July 2025',
  time: '14:00',
  location: 'Bedford, East of England',
  temperature: 29,
  feelsLike: 29,
  overnight: 17,
  spellDay: 3,
  alert: 'No heat-health alert issued',
  condition: 'Clear sky · 7 hours above 26°C',
}

export interface CompanionViewProps {
  /** Which tab to show by default. */
  defaultAudience: Audience
  /** Page-level label shown above the profile name. */
  viewLabel: string
  /** The other route — links to it in the header. */
  otherRoute: { href: string; label: string }
}

export default function CompanionView({
  defaultAudience,
  viewLabel,
  otherRoute,
}: CompanionViewProps) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [result, setResult] = useState<Result | null>(null)
  const [stale, setStale] = useState(false)
  const [failed, setFailed] = useState(false)
  const [audience, setAudience] = useState<Audience>(defaultAudience)
  // Heatwave scenario is the default — it is the demo's point.
  const [heatScenario, setHeatScenario] = useState(true)

  useEffect(() => {
    setProfile(loadProfile())
    if (typeof window !== 'undefined') {
      const demo = new URLSearchParams(window.location.search).get('demo')
      if (demo === 'live') setHeatScenario(false)
    }
  }, [])

  const load = useCallback(async (p: Profile, scenario: boolean) => {
    const cacheKey = scenario ? `${CACHE_KEY}:heat` : CACHE_KEY
    const cached =
      typeof localStorage !== 'undefined' ? localStorage.getItem(cacheKey) : null
    if (cached) {
      try {
        setResult(JSON.parse(cached) as Result)
        setStale(true)
      } catch {
        /* corrupt cache */
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
          Tell us about the person you look after and we can tell you whether tonight is safe for
          them.
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
  const fx = HEAT_FIXTURE_CONTEXT

  return (
    <main className="mx-auto max-w-[30rem] px-5 pb-24 pt-8">
      <div className="mb-1 flex items-center justify-between gap-2">
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] faint">
          Climatise · {viewLabel}
        </p>
        <Link
          href={otherRoute.href}
          className="text-[12px] faint underline decoration-dotted"
          style={{ color: 'var(--accent)' }}
        >
          {otherRoute.label}
        </Link>
      </div>

      <h1 className="mt-1 text-[21px] font-semibold tracking-tight">
        {defaultAudience === 'cared_for'
          ? `Your situation tonight`
          : `Is it safe for ${result.profile.name} tonight?`}
      </h1>

      {/* ── Heatwave scenario: in-the-moment weather panel ────────────── */}
      <div
        className="mt-4 overflow-hidden rounded-[var(--radius-lg)] border"
        style={{
          borderColor: heatScenario ? '#d97706' : 'var(--line)',
          background: heatScenario ? '#fffbeb' : 'var(--surface)',
        }}
      >
        {heatScenario ? (
          <div className="p-3.5">
            {/* Date / location row */}
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[12px] font-semibold" style={{ color: '#92400e' }}>
                  {fx.date} · {fx.time} · {fx.location}
                </p>
                <p className="mt-0.5 text-[12px]" style={{ color: '#78350f' }}>
                  {fx.condition}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setHeatScenario(false)}
                className="btn btn-ghost shrink-0 px-2.5 py-1 text-[12px]"
                style={{ minHeight: 'auto', color: '#92400e' }}
              >
                Show live
              </button>
            </div>
            {/* Temperature row */}
            <div
              className="mt-2.5 flex items-center gap-4 rounded-lg px-3 py-2"
              style={{ background: '#fef3c7' }}
            >
              <div className="text-center">
                <p className="text-[28px] font-bold leading-none" style={{ color: '#92400e' }}>
                  {fx.temperature}°
                </p>
                <p className="text-[11px]" style={{ color: '#78350f' }}>
                  feels like {fx.feelsLike}°C
                </p>
              </div>
              <div className="flex-1 space-y-0.5 text-[12px]" style={{ color: '#78350f' }}>
                <p>
                  🌙 Tonight: {fx.overnight}°C — <strong>no overnight recovery</strong>
                </p>
                <p>
                  📅 Day {fx.spellDay} of sustained heat — risk builds across a spell
                </p>
                <p className="font-semibold" style={{ color: '#b45309' }}>
                  ⚠ {fx.alert}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3 p-3.5">
            <p className="text-[13px] faint">Showing live weather today.</p>
            <button
              type="button"
              onClick={() => setHeatScenario(true)}
              className="btn btn-ghost shrink-0 px-3 py-1.5 text-[13px]"
              style={{ minHeight: 'auto' }}
            >
              19 Jul 2025
            </button>
          </div>
        )}
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

      {/* ── Tier badge ──────────────────────────────────────────────────── */}
      <section className={`card mt-5 p-5 tone-${tier.tone}`}>
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className={`glyph glyph-${tier.shape}`} />
          <span className="text-[22px] font-bold tracking-tight">{a.tier}</span>
        </div>
        <p className="mt-2.5 text-[15px] muted">{tier.act}</p>

        <dl className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-lg">
          {(
            [
              ['exposure', a.exposureScore],
              ['vulnerability', a.vulnerabilityScore],
              ['risk score', a.riskScore.toFixed(1)],
            ] as [string, number | string][]
          ).map(([label, value]) => (
            <div key={label} className="bg-[var(--panel-2)] px-3 py-2.5">
              <dd className="font-mono text-[16px] tabular-nums">{value}</dd>
              <dt className="mt-0.5 text-[11px] faint">{label}</dt>
            </div>
          ))}
        </dl>

        <p className="mt-3 text-[12.5px] faint">
          Bedroom tonight,{' '}
          <span
            title="Estimated from the forecast and their home, not measured"
            className="underline decoration-dotted"
          >
            modelled
          </span>{' '}
          at {a.indoorNightEstimateModelled}°C · forecast {a.source}
        </p>
      </section>

      {/* ── Why ─────────────────────────────────────────────────────────── */}
      <Section title="Why">
        {a.reasons.map((r) => (
          <div key={r.code} className="row">
            <span className="float-right font-mono text-[11px] tabular-nums faint">
              +{r.weight}
            </span>
            <p className="text-[15px] font-semibold">{r.title}</p>
            <p className="mt-1 text-[13.5px] muted">{r.explanation}</p>
          </div>
        ))}
      </Section>

      {/* ── What to do ──────────────────────────────────────────────────── */}
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
              Nothing here is written for {result.profile.name} to act on. Advice they cannot act
              on themselves is addressed to you instead.
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

      {/* ── Watch for ───────────────────────────────────────────────────── */}
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
        <strong>Demonstrator only.</strong> Not medical advice and not clinically validated. Never
        change a prescribed medicine on the basis of this app — speak to a pharmacist or GP.
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
