'use client'

import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'

import Assistant from '@/components/Assistant'
import RegionPanel from '@/components/RegionPanel'
import type { MapRegion } from '@/components/UKMap'
import { clearProfile, loadProfile, saveProfile } from '@/lib/client-store'
import { DEMO_PROFILES, type Profile } from '@/lib/profile'
import { regionByCode } from '@/lib/regions'
import { assessRisk, BAND_COLOURS, bandLabel } from '@/lib/risk'
import { HEAT_FIXTURE_REGIONS, type HeatRegion } from '@/lib/heat-fixture'
import type { RegionWeather } from '@/lib/weather'

type ApiRegion = RegionWeather & MapRegion & { conditions: string }

// Leaflet touches `window` on import, so it can never be server-rendered.
const UKMap = dynamic(() => import('@/components/UKMap'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[15px] faint">Loading map…</div>
  ),
})

export default function HomePage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [ready, setReady] = useState(false)
  const [liveRegions, setLiveRegions] = useState<ApiRegion[]>([])
  const [fetchedAt, setFetchedAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedCode, setSelectedCode] = useState<string | null>(null)
  const [tab, setTab] = useState<'advice' | 'assistant'>('advice')
  // Heatwave scenario default — same as /personal and /caregiver.
  const [heatScenario, setHeatScenario] = useState(true)

  const regions: ApiRegion[] = heatScenario
    ? (HEAT_FIXTURE_REGIONS as unknown as ApiRegion[])
    : liveRegions

  useEffect(() => {
    const stored = loadProfile()
    setProfile(stored)
    setSelectedCode(stored?.regionCode ?? null)
    setReady(true)
  }, [])

  useEffect(() => {
    let cancelled = false
    fetch('/api/regions')
      .then(async (r) => {
        const body = await r.json()
        if (!r.ok) throw new Error(body.error ?? `Weather service returned ${r.status}`)
        return body
      })
      .then((body) => {
        if (cancelled) return
        setLiveRegions(body.regions)
        setFetchedAt(body.fetchedAt)
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const switchToDemo = useCallback((demo: Profile) => {
    saveProfile(demo)
    setProfile(demo)
    setSelectedCode(demo.regionCode)
    setTab('advice')
  }, [])

  const selectedRegion = useMemo(
    () => regions.find((r) => r.regionCode === selectedCode) ?? null,
    [regions, selectedCode],
  )

  const myRegion = useMemo(
    () => regions.find((r) => r.regionCode === profile?.regionCode) ?? null,
    [regions, profile],
  )

  const myAssessment = useMemo(
    () => (profile && myRegion ? assessRisk(profile, myRegion) : null),
    [profile, myRegion],
  )

  const suggestions = useMemo(() => {
    if (!myAssessment) return ['What should I do today?']
    const base = ['What should I do right now?']
    if (myAssessment.direction === 'heat') {
      base.push('How do I cool my home down?', 'How much should I be drinking?')
    } else if (myAssessment.direction === 'cold') {
      base.push('Which room should I heat?', 'How do I keep my heating bill down?')
    } else {
      base.push('What should I watch out for later?')
    }
    if (myAssessment.worseningToday) base.push('What changes later today?')
    return base
  }, [myAssessment])

  if (!ready) {
    return (
      <main className="flex min-h-dvh items-center justify-center">
        <p className="text-[15px] faint">Loading…</p>
      </main>
    )
  }

  if (!profile) return <Welcome onPickDemo={switchToDemo} />

  const bandColour = myAssessment ? BAND_COLOURS[myAssessment.band] : undefined

  return (
    <main className="mx-auto flex min-h-dvh max-w-[34rem] flex-col">
      {/* Heatwave / live toggle — sticky at top, above the header */}
      <div
        className="flex items-center justify-between gap-3 border-b px-4 py-2"
        style={{
          borderColor: heatScenario ? '#d97706' : 'var(--line)',
          background: heatScenario ? '#fffbeb' : 'var(--surface)',
        }}
      >
        <p className="text-[12px]" style={{ color: heatScenario ? '#92400e' : 'var(--ink-faint)' }}>
          {heatScenario
            ? '☀️ 19 July 2025 · 29°C peak · No heat-health alert issued · 146 excess deaths'
            : 'Showing live weather today.'}
        </p>
        <button
          type="button"
          onClick={() => setHeatScenario((v) => !v)}
          className="btn btn-ghost shrink-0 px-2.5 py-1 text-[12px]"
          style={{ minHeight: 'auto', color: heatScenario ? '#92400e' : undefined }}
        >
          {heatScenario ? 'Show live' : '19 Jul 2025'}
        </button>
      </div>

      <header
        className="flex items-center justify-between gap-3 border-b px-5 py-4"
        style={{ borderColor: 'var(--line)' }}
      >
        <div className="min-w-0">
          <h1 className="truncate text-[21px] font-bold">
            Hello, {profile.name}
            {profile.isDemo && (
              <span
                className="ml-2 rounded-full px-2 py-0.5 align-middle text-[12px] font-semibold uppercase tracking-wide"
                style={{ background: 'var(--accent-wash)', color: 'var(--accent)' }}
              >
                Demo
              </span>
            )}
          </h1>
          <p className="mt-0.5 flex items-center gap-2 truncate text-[15px] muted">
            {bandColour && (
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: bandColour }}
                aria-hidden="true"
              />
            )}
            <span className="truncate">
              {regionByCode(profile.regionCode)?.name ?? profile.regionCode}
              {myAssessment && ` — ${bandLabel(myAssessment.band)}`}
            </span>
          </p>
        </div>
        <button
          onClick={() => {
            clearProfile()
            setProfile(null)
          }}
          className="btn btn-ghost shrink-0 px-3"
          style={{ minHeight: 'auto', paddingTop: '0.4rem', paddingBottom: '0.4rem' }}
        >
          Switch
        </button>
      </header>

      {/* The UK is tall and narrow, so a short map wastes most of its width. */}
      <div
        className="relative h-[42dvh] min-h-[270px] shrink-0"
        style={{ background: 'var(--paper-sunk)' }}
      >
        {error ? (
          <div
            className="flex h-full items-center justify-center px-6 text-center text-[15px]"
            style={{ color: 'var(--danger)' }}
          >
            {error}
          </div>
        ) : (
          <UKMap
            regions={regions}
            myRegionCode={profile.regionCode}
            selectedRegionCode={selectedCode ?? undefined}
            onSelectRegion={setSelectedCode}
          />
        )}
        {regions.length > 0 && <Legend />}
      </div>

      {/* Tabs only where there is not room for both. Above `lg` the advice and
          the assistant sit side by side: a question is almost always *about* the
          advice, and hiding one to read the other means answering from memory. */}
      <nav
        className="flex gap-1 border-y px-4 pt-2.5 xl:hidden"
        style={{ borderColor: 'var(--line)' }}
        role="tablist"
      >
        {(
          [
            ['advice', 'Your advice'],
            ['assistant', 'Ask a question'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className="relative px-3 pb-2.5 font-semibold transition-opacity"
            style={{ opacity: tab === id ? 1 : 0.5 }}
          >
            {label}
            {tab === id && (
              <span
                className="absolute inset-x-0 -bottom-px h-[3px] rounded-full"
                style={{ background: 'var(--accent)' }}
              />
            )}
          </button>
        ))}
      </nav>

      <div className="flex min-h-0 flex-1">
        {/* Below `lg` the inactive panel is hidden rather than unmounted, so
            switching tabs does not discard a conversation already in progress. */}
        <div
          className={`min-h-0 flex-1 overflow-y-auto xl:block xl:min-w-[34rem] ${
            tab === 'advice' ? '' : 'hidden'
          }`}
        >
          <RegionPanel
            profile={profile}
            region={selectedRegion}
            isOwnRegion={selectedRegion?.regionCode === profile.regionCode}
            fetchedAt={fetchedAt}
          />
        </div>
        <div
          className={`min-h-0 flex-1 border-l xl:flex xl:w-[24rem] xl:shrink-0 xl:grow-0 xl:flex-col ${
            tab === 'assistant' ? 'flex flex-col' : 'hidden xl:flex'
          }`}
          style={{ borderColor: 'var(--line)' }}
        >
          <Assistant profile={profile} suggestions={suggestions} heatScenario={heatScenario} />
        </div>
      </div>
    </main>
  )
}

function Legend() {
  return (
    <div
      className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-medium"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      <span className="faint">Cold</span>
      <span className="flex overflow-hidden rounded-full" aria-hidden="true">
        {['cold-severe', 'cold-high', 'cold-moderate', 'comfortable', 'heat-moderate', 'heat-high', 'heat-severe'].map(
          (band) => (
            <span
              key={band}
              className="h-2.5 w-3.5"
              style={{ background: BAND_COLOURS[band as keyof typeof BAND_COLOURS] }}
            />
          ),
        )}
      </span>
      <span className="faint">Hot</span>
    </div>
  )
}

function Welcome({ onPickDemo }: { onPickDemo: (p: Profile) => void }) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-[34rem] flex-col px-5 py-10">
      <div className="flex-1">
        <div className="mb-8 flex items-center gap-3">
          <Mark />
          <span className="text-[19px] font-bold tracking-tight">Climatise</span>
        </div>

        <h1 className="mb-4 text-[34px] font-bold">
          Too hot or too cold — for <em>you</em>, not for the average person.
        </h1>
        <p className="mb-9 text-[18px] muted">
          The same weather is harmless for one person and dangerous for another. Tell us a little
          about yourself and we&apos;ll tell you what to actually do about it, anywhere in the UK.
        </p>

        <Link href="/onboarding" className="btn btn-primary mb-3 w-full text-[18px]">
          Get started
        </Link>
        <p className="mb-10 text-center text-[15px] faint">
          Takes about 30 seconds. No account, no password.
        </p>

        <div>
          <h2 className="mb-1 font-semibold">Or have a look round as someone else</h2>
          <p className="mb-4 text-[16px] muted">
            Five people, five parts of the UK, the same weather — and five different answers.
          </p>
          <div className="space-y-2.5">
            {DEMO_PROFILES.map((demo) => (
              <button
                key={demo.id}
                onClick={() => onPickDemo(demo)}
                className="choice flex-col items-stretch"
              >
                <span className="mb-0.5 flex items-baseline gap-2">
                  <span className="font-semibold">{demo.name}</span>
                  <span className="text-[15px] faint">{regionByCode(demo.regionCode)?.name}</span>
                </span>
                <span className="text-[15px] muted">{demo.notes}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="mt-10 text-[14px] faint">
        General guidance only — not medical advice. In an emergency call 999, or 111 for urgent
        advice.
      </p>
    </main>
  )
}

/** The cold/heat split mark, matching the app icon. */
function Mark() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--ink)" />
      <path d="M16 7a9 9 0 000 18z" fill="#4e8fc4" />
      <path d="M16 7a9 9 0 010 18z" fill="#e07a3f" />
      <rect x="14.6" y="5.5" width="2.8" height="21" rx="1.4" fill="var(--paper)" />
    </svg>
  )
}
