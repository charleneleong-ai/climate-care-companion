'use client'

/**
 * The companion screen.
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

import AppShell from '@/components/AppShell'
import { loadPersona, loadProfile, type SignedInPersona } from '@/lib/client-store'
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

interface Checkin {
  channel: string
  outcome: 'completed' | 'abandoned' | 'no_answer'
  started_at: string
  answered: number
  asked: number
  red_flags: string[]
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
  const [persona, setPersona] = useState<SignedInPersona | null>(null)
  const [identified, setIdentified] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [stale, setStale] = useState(false)
  const [failed, setFailed] = useState(false)
  const [audience, setAudience] = useState<'caregiver' | 'cared_for'>('caregiver')
  const [checkins, setCheckins] = useState<Checkin[]>([])
  // The heatwave scenario is the default — a Low tier on a mild day demonstrates
  // nothing. ?demo=live switches to current conditions.
  const [heatScenario, setHeatScenario] = useState(true)

  useEffect(() => {
    setPersona(loadPersona())
    setProfile(loadProfile())
    if (typeof window !== 'undefined') {
      const demo = new URLSearchParams(window.location.search).get('demo')
      if (demo === 'live') setHeatScenario(false)
    }
    setIdentified(true)
  }, [])

  const load = useCallback(async (request: () => Promise<Response>) => {
    // NFR-04: show the last answer straight away rather than a spinner. A
    // caregiver on a bad connection gets something they can act on, labelled
    // as stale, instead of nothing.
    const cached = typeof localStorage !== 'undefined' ? localStorage.getItem(CACHE_KEY) : null
    if (cached) {
      try {
        setResult(JSON.parse(cached) as Result)
        setStale(true)
      } catch {
        /* a corrupt cache is not worth reporting — it is about to be replaced */
      }
    }

    try {
      const response = await request()
      const body = (await response.json()) as Result
      if (!response.ok) throw new Error(body.error ?? String(response.status))
      if (body.error) throw new Error(body.error)

      setResult(body)
      setStale(false)
      setFailed(false)
      localStorage.setItem(CACHE_KEY, JSON.stringify(body))
    } catch {
      setFailed(true)
    }
  }, [])

  useEffect(() => {
    // A persona and a personal profile are mutually exclusive, and the persona
    // wins — it is the identity most recently chosen.
    const scenario = heatScenario ? '&demo=heat' : ''
    if (persona) {
      void load(() =>
        fetch(`/api/personas/${persona.id}?audience=${audience}${scenario}`),
      )
    } else if (profile) {
      void load(() =>
        fetch(`/api/assess${heatScenario ? '?demo=heat' : ''}`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ profile }),
        }),
      )
    }
  }, [persona, profile, audience, heatScenario, load])

  useEffect(() => {
    const id = persona?.id ?? profile?.id
    if (!id) return
    fetch(`/api/checkins/${id}`)
      .then((r) => r.json())
      .then((body) => setCheckins(body.checkins ?? []))
      .catch(() => setCheckins([]))
  }, [persona, profile])

  // Until localStorage has been read, "nobody is set up" is not yet true — and
  // flashing the empty state at a returning user reads as data loss.
  if (!identified) return <AppShell title="Climatise">{null}</AppShell>

  if (!profile && !persona) {
    return (
      <AppShell title="Welcome">
        <h2 className="text-[17px] font-semibold">No one set up yet</h2>
        <p className="mt-2 text-[16px] muted">
          Tell us about the person you look after and we can tell you whether tonight is
          safe for them.
        </p>
        <Link href="/signin" className="btn btn-secondary mt-4 inline-flex">
          Or sign in as a demo person
        </Link>
        <Link href="/onboarding" className="btn btn-primary mt-6 inline-flex">
          Set up
        </Link>
      </AppShell>
    )
  }

  if (!result) {
    return (
      <AppShell title="Checking…">
        <p className="text-[16px] muted">
          {failed ? 'Cannot reach the risk service, and nothing is saved yet.' : 'Checking…'}
        </p>
      </AppShell>
    )
  }

  const a = result.assessment
  const tier = TIER[a.tier]
  const plan = result.plan
  const visible = plan.items.filter((item) => item.text)

  return (
    <AppShell title={`Is it safe for ${result.profile.name} tonight?`}>
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
      <section className={`card p-5 tone-${tier.tone}`}>
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

      {checkins.length > 0 && <LastCheckin checkin={checkins[checkins.length - 1]} />}

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
    </AppShell>
  )
}

const OUTCOME_LABEL: Record<Checkin['outcome'], string> = {
  completed: 'Answered',
  abandoned: 'Started but not finished',
  no_answer: 'No answer',
}

function LastCheckin({ checkin }: { checkin: Checkin }) {
  const when = new Date(checkin.started_at)
  const missed = checkin.outcome !== 'completed'
  return (
    <section className="mt-6">
      <h2 className="section-label">Last check-in</h2>
      <div className="card p-4">
        <p className="text-[15px]">
          <strong>{OUTCOME_LABEL[checkin.outcome]}</strong> · by {checkin.channel} ·{' '}
          {when.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
        </p>
        {checkin.outcome === 'completed' && (
          <p className="mt-1 text-[13.5px] muted">
            {checkin.answered} of {checkin.asked} questions answered.
          </p>
        )}
        {missed && (
          /* A missed check-in during a risk window is the condition the whole
             escalation ladder exists for, so it is stated rather than hidden. */
          <p className="mt-1 text-[13.5px] muted">
            Nobody has confirmed how they are. Consider checking in person.
          </p>
        )}
        {checkin.red_flags.length > 0 && (
          <p className="mt-2 text-[14px]" style={{ color: 'var(--danger)' }}>
            They reported: {checkin.red_flags.join(', ')}.
          </p>
        )}
      </div>
    </section>
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
