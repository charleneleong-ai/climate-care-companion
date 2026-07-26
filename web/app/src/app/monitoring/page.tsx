'use client'

/**
 * /monitoring — population-level dashboard.
 *
 * Shows the national picture on 19 July 2025: what the national alerting
 * cascade said (nothing), what this system would have found (5 of 8 demo
 * profiles at HIGH risk), and the death count context from UKHSA data.
 *
 * This is the clinical/policy view — the argument for why individual-level
 * risk assessment matters even when there is no regional alert.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

// ── Static data for 19 July 2025 ─────────────────────────────────────────────
// Sources: UKHSA Heat Mortality Monitoring Report 2025, LSHTM/Imperial/Met Office.

const SCENARIO = {
  date: 'Saturday 19 July 2025',
  location: 'England',
  peak: '29°C',
  overnight: '17°C — no overnight recovery',
  spellDay: 3,
  alert: 'None',
  alertDetail: 'No heat-health alert was issued in any English region on this date.',
}

const STATS = [
  {
    value: '146',
    label: 'estimated excess deaths',
    sub: 'Episode 4 · England · 17–19 July 2025',
    colour: '#c1362f',
  },
  {
    value: '0',
    label: 'regional heat-health alerts issued',
    sub: 'UKHSA alert level: NONE across all regions',
    colour: '#2563eb',
  },
  {
    value: '5 / 8',
    label: 'demo profiles at HIGH or above',
    sub: 'Assessed individually — the cascade saw nothing',
    colour: '#d97706',
  },
  {
    value: '2,295',
    label: 'total heat deaths, summer 2025',
    sub: 'Highest since 2022 (2,985) · UKHSA 2025 report',
    colour: '#7c3aed',
  },
]

// Demo cohort results on that day, pre-computed so the monitoring page loads
// instantly with no API call. Source: demo_compare.py against the fixture.
const COHORT: {
  name: string
  condition: string
  tier: 'Elevated' | 'High'
  vuln: number
  interactions: number
  note: string
}[] = [
  {
    name: 'Doris',
    condition: 'Dementia · COPD',
    tier: 'High',
    vuln: 13,
    interactions: 11,
    note: 'Cannot self-report, cannot self-rescue',
  },
  {
    name: 'Victor',
    condition: 'Cardiovascular · Renal · COPD',
    tier: 'High',
    vuln: 14,
    interactions: 14,
    note: '"Drink plenty" is the wrong advice for him',
  },
  {
    name: 'Sylvia',
    condition: 'Cardiovascular',
    tier: 'High',
    vuln: 11,
    interactions: 10,
    note: 'Body warning signs switched off by medication',
  },
  {
    name: 'Elsie',
    condition: 'Dementia · Cardiovascular',
    tier: 'High',
    vuln: 13,
    interactions: 4,
    note: 'Lithium toxicity risk — cannot self-report tremor',
  },
  {
    name: 'Iris',
    condition: 'Cardiovascular · Renal',
    tier: 'High',
    vuln: 12,
    interactions: 4,
    note: 'Silent overheater — no sweat, cannot self-rescue',
  },
  {
    name: 'Alan',
    condition: 'Cardiovascular',
    tier: 'Elevated',
    vuln: 3,
    interactions: 2,
    note: 'Same diagnosis as Victor, fraction of the risk',
  },
  {
    name: 'Pat',
    condition: 'Dementia',
    tier: 'Elevated',
    vuln: 2,
    interactions: 1,
    note: 'Same condition as Doris — caregiver present',
  },
  {
    name: 'Ben',
    condition: 'Cardiovascular',
    tier: 'Elevated',
    vuln: 5,
    interactions: 5,
    note: 'Low score — but insulin storage failure is life-critical',
  },
]

const TIER_COLOUR: Record<string, string> = {
  High: '#c1362f',
  Elevated: '#d97706',
  Low: '#7fb069',
}

export default function MonitoringPage() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    // Stagger-in for the demo
    const t = setTimeout(() => setShow(true), 60)
    return () => clearTimeout(t)
  }, [])

  const high = COHORT.filter((p) => p.tier === 'High').length
  const elevated = COHORT.filter((p) => p.tier === 'Elevated').length

  return (
    <main className="mx-auto max-w-[38rem] px-5 pb-24 pt-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] faint">
            Climatise · monitoring
          </p>
          <h1 className="mt-1 text-[21px] font-semibold tracking-tight">
            {SCENARIO.date}
          </h1>
          <p className="mt-0.5 text-[15px] muted">{SCENARIO.location}</p>
        </div>
        <Link href="/" className="btn btn-ghost px-3 py-1.5 text-[13px]" style={{ minHeight: 'auto' }}>
          ← Map
        </Link>
      </div>

      {/* Scenario context */}
      <div
        className="mt-4 rounded-[var(--radius-lg)] border p-4"
        style={{ borderColor: '#d97706', background: '#fffbeb' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[18px]"
            style={{ background: '#fef3c7' }}
          >
            ☀️
          </div>
          <div>
            <p className="text-[13px] font-semibold" style={{ color: '#92400e' }}>
              {SCENARIO.peak} peak · overnight {SCENARIO.overnight} · Day {SCENARIO.spellDay} of
              sustained heat
            </p>
            <p className="mt-0.5 text-[12px]" style={{ color: '#78350f' }}>
              <strong style={{ color: '#b45309' }}>
                National alert: {SCENARIO.alert}
              </strong>{' '}
              — {SCENARIO.alertDetail}
            </p>
          </div>
        </div>
      </div>

      {/* Stats grid */}
      <div className="mt-5 grid grid-cols-2 gap-3">
        {STATS.map((s) => (
          <div
            key={s.label}
            className="card p-4"
            style={{ borderLeft: `3px solid ${s.colour}` }}
          >
            <p
              className="font-mono text-[28px] font-bold leading-none tabular-nums"
              style={{ color: s.colour }}
            >
              {s.value}
            </p>
            <p className="mt-1 text-[13px] font-semibold">{s.label}</p>
            <p className="mt-0.5 text-[11px] faint">{s.sub}</p>
          </div>
        ))}
      </div>

      {/* Cohort breakdown */}
      <section className="mt-6">
        <h2 className="section-label">Demo cohort · individual assessment</h2>
        <p className="mb-3 text-[13px] muted">
          All assessed against the same date, same weather.{' '}
          <strong>{high} HIGH</strong> · {elevated} Elevated · 0 alerts issued by the national
          cascade.
        </p>
        <div className="card divide-y divide-[var(--line)]">
          {COHORT.map((p) => (
            <div key={p.name} className="flex items-start gap-3 px-4 py-3">
              <div
                className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: TIER_COLOUR[p.tier] ?? '#ccc' }}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <p className="text-[15px] font-semibold">{p.name}</p>
                  <p
                    className="text-[12px] font-semibold"
                    style={{ color: TIER_COLOUR[p.tier] }}
                  >
                    {p.tier}
                  </p>
                  <p className="ml-auto font-mono text-[11px] faint">
                    vuln {p.vuln} · {p.interactions} actions
                  </p>
                </div>
                <p className="text-[12px] faint">{p.condition}</p>
                <p className="mt-0.5 text-[12px] muted">{p.note}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* The gap */}
      <section className="mt-6">
        <h2 className="section-label">The gap this system closes</h2>
        <div className="card divide-y divide-[var(--line)]">
          {[
            {
              label: 'National alerting cascade',
              value: 'Nothing to do — no alert issued',
              detail:
                'UKHSA → NHS England → integrated care boards → providers. No final link to individuals or unpaid carers.',
              bad: true,
            },
            {
              label: 'This system',
              value: `5 people at HIGH risk identified`,
              detail:
                'Computed individually: age, conditions, medications, housing, living situation — regardless of whether a regional alert was issued.',
              bad: false,
            },
          ].map((row) => (
            <div key={row.label} className="px-4 py-3">
              <p className="text-[12px] font-semibold uppercase tracking-wide faint">
                {row.label}
              </p>
              <p
                className="mt-0.5 text-[15px] font-semibold"
                style={{ color: row.bad ? '#6b7280' : '#059669' }}
              >
                {row.value}
              </p>
              <p className="mt-0.5 text-[12.5px] muted">{row.detail}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Quick links */}
      <div className="mt-8 flex gap-3">
        <Link href="/caregiver" className="btn btn-primary flex-1 text-center">
          Caregiver view
        </Link>
        <Link href="/personal" className="btn btn-secondary flex-1 text-center">
          Personal view
        </Link>
      </div>

      <ForecastHorizon />

      <p className="mt-6 text-[12px] faint">
        Death counts from UKHSA <em>Heat mortality monitoring report, England: 2025</em> (Crown
        copyright, OGL v3). Cohort tiers computed by the Climatise risk engine against the Bedford
        19 July 2025 fixture. All personas are fictional (SC-6).
      </p>
    </main>
  )
}


// ── Live forecast horizon ────────────────────────────────────────────────────

interface ForecastDay {
  date: string
  lead_days: number
  peak_air: number | null
  tiers: Record<string, number>
  at_risk: number
}

interface FirstAtRisk {
  person_id: string
  name: string
  date: string
  lead_days: number
}

const TIER_ORDER = ['Severe', 'High', 'Elevated', 'Low'] as const

const TIER_TONE: Record<string, string> = {
  Low: '#7fb069',
  Elevated: '#f3c05a',
  High: '#e07a3f',
  Severe: '#c1362f',
}

function ForecastHorizon() {
  const [days, setDays] = useState<ForecastDay[]>([])
  const [first, setFirst] = useState<FirstAtRisk[]>([])
  const [registerSize, setRegisterSize] = useState(0)
  const [label, setLabel] = useState('')
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    fetch('/api/monitoring')
      .then((r) => r.json())
      .then((body) => {
        setDays(body.days ?? [])
        setFirst(body.first_at_risk ?? [])
        setRegisterSize(body.register_size ?? 0)
        setLabel(body.label ?? '')
        setUnavailable(Boolean(body.unavailable))
      })
      .catch(() => setUnavailable(true))
  }, [])

  if (unavailable) {
    return (
      <section className="mt-10">
        <h2 className="section-label">The days ahead</h2>
        <p className="text-[15px] muted">
          No forecast available right now, so this section is empty rather than
          estimated.
        </p>
      </section>
    )
  }

  if (days.length === 0) return null


  return (
    <section className="mt-10">
      <h2 className="section-label">The days ahead</h2>
      <p className="mb-1 text-[15px] muted">
        Every one of the {registerSize} people on the register, scored against each
        day of the episode. {label}
      </p>
      <p className="mb-4 text-[15px] muted">
        The register is quiet for two days and then it is not. Nothing about the
        third day was a surprise on the first — which is the whole argument for
        assessing ahead rather than reporting after.
      </p>

      <div className="card p-4">
        <ol className="flex flex-col gap-3">
          {days.map((day) => {
            const when = new Date(day.date)
            return (
              <li key={day.date} className="flex items-center gap-3">
                <span className="w-[5.5rem] shrink-0 text-[13px] tabular-nums">
                  {when.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}
                </span>
                <span className="w-[3.5rem] shrink-0 font-mono text-[13px] tabular-nums faint">
                  {day.peak_air === null ? '—' : `${day.peak_air.toFixed(1)}°`}
                </span>
                {/* Stacked by tier: a day where six people are High is a
                    different day from one where twelve are Elevated, and a
                    single count cannot tell them apart. */}
                <span aria-hidden="true" className="flex h-3 flex-1 overflow-hidden rounded-full"
                      style={{ background: 'var(--line)' }}>
                  {TIER_ORDER.map((tier) => {
                    const n = day.tiers[tier] ?? 0
                    if (n === 0) return null
                    return (
                      <span
                        key={tier}
                        style={{
                          width: `${(n / registerSize) * 100}%`,
                          background: TIER_TONE[tier],
                        }}
                      />
                    )
                  })}
                </span>
                <span className="w-[7.5rem] shrink-0 text-right text-[13px] tabular-nums">
                  {day.at_risk > 0 ? (
                    <strong>{day.at_risk} of {registerSize} at risk</strong>
                  ) : (
                    <span className="faint">none at risk</span>
                  )}
                </span>
              </li>
            )
          })}
        </ol>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
        {TIER_ORDER.map((tier) => (
          <span key={tier} className="flex items-center gap-1.5 text-[12px] faint">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm"
                  style={{ background: TIER_TONE[tier] }} />
            {tier}
          </span>
        ))}
      </div>

      {first.length > 0 && (
        <>
          <h3 className="section-label mt-6">Who crosses first, and how long there is</h3>
          <div className="card">
            {first.slice(0, 8).map((person) => (
              <p key={person.person_id} className="row flex items-baseline justify-between gap-3">
                <span className="text-[15px] font-semibold">{person.name}</span>
                <span className="text-[13.5px] muted">
                  {new Date(person.date).toLocaleDateString('en-GB', { weekday: 'long' })} ·{' '}
                  <strong>
                    {person.lead_days === 0
                      ? 'today'
                      : `${person.lead_days} day${person.lead_days === 1 ? '' : 's'} notice`}
                  </strong>
                </span>
              </p>
            ))}
          </div>
          <p className="mt-2.5 text-[13px] faint">
            Lead time is the whole argument. Tablets can be moved off a windowsill
            and a fluid plan settled with a pharmacist two days out. The same
            information on the final evening is a report, not a prevention — and
            no regional alert was issued on any of these three days.
          </p>
        </>
      )}
    </section>
  )
}
