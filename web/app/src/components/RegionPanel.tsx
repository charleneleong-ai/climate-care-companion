'use client'

import { getAdvice } from '@/lib/advice'
import type { Profile } from '@/lib/profile'
import { regionByCode } from '@/lib/regions'
import { assessRisk, BAND_COLOURS, bandLabel, type RiskBand } from '@/lib/risk'
import type { RegionWeather } from '@/lib/weather'

interface Props {
  profile: Profile
  region: (RegionWeather & { conditions: string; band: RiskBand; severity: number }) | null
  /** Advice is only personalised for the user's own region. */
  isOwnRegion: boolean
  fetchedAt: string | null
}

/** Dot colour per priority. Paired with a text label, never colour alone. */
const PRIORITY_COLOUR = {
  critical: 'var(--danger)',
  important: '#c26a2f',
  helpful: 'var(--line-strong)',
} as const

export default function RegionPanel({ profile, region, isOwnRegion, fetchedAt }: Props) {
  if (!region) {
    return (
      <div className="px-5 py-6 text-[16px] muted">
        Tap a region on the map to see its conditions.
      </div>
    )
  }

  const regionName = regionByCode(region.regionCode)?.name ?? region.regionCode

  // For the user's own region we run their personal assessment; elsewhere we
  // show the region's own conditions without pretending the advice applies to
  // them somewhere they aren't.
  const assessment = isOwnRegion ? assessRisk(profile, region) : null
  const advice = assessment ? getAdvice(assessment) : null
  const displayBand = assessment?.band ?? region.band
  const bandColour = BAND_COLOURS[displayBand]

  return (
    <div className="overflow-y-auto px-5 py-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-[22px] font-bold">{regionName}</h2>
          <p className="mt-0.5 text-[15px] muted">
            {region.conditions} · {Math.round(region.humidity)}% humidity ·{' '}
            {Math.round(region.windSpeed)} km/h wind
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[34px] font-bold leading-none">
            {Math.round(region.apparentTemperature)}°
          </p>
          <p className="text-[14px] faint">
            feels like
            {Math.abs(region.apparentTemperature - region.temperature) >= 1 &&
              ` (air ${Math.round(region.temperature)}°)`}
          </p>
        </div>
      </div>

      <div
        className="mb-5 rounded-[var(--radius-lg)] px-4 py-3.5"
        style={{ background: `${bandColour}22`, border: `1px solid ${bandColour}55` }}
      >
        <div className="flex items-center gap-2.5">
          <span
            className="h-3.5 w-3.5 shrink-0 rounded-full"
            style={{ background: bandColour }}
            aria-hidden="true"
          />
          <p className="font-semibold">{advice ? advice.headline : bandLabel(displayBand)}</p>
        </div>
        {advice ? (
          <p className="mt-1.5 text-[16px]">{advice.summary}</p>
        ) : (
          <p className="mt-1.5 text-[16px] muted">
            Today {Math.round(region.todayMin)}° to {Math.round(region.todayMax)}°. This is how it
            feels for an average adult — your own advice is for{' '}
            {regionByCode(profile.regionCode)?.name}.
          </p>
        )}
      </div>

      {advice?.urgentWarning && (
        <div
          role="alert"
          className="mb-5 rounded-[var(--radius-lg)] px-4 py-3.5 text-[16px]"
          style={{
            background: 'var(--danger-wash)',
            border: '2px solid var(--danger)',
          }}
        >
          <strong className="mb-1 block" style={{ color: 'var(--danger)' }}>
            Get help if you see this
          </strong>
          {advice.urgentWarning}
        </div>
      )}

      {advice && advice.actions.length > 0 && (
        <section className="mb-5">
          <h3 className="mb-2.5 text-[15px] font-semibold uppercase tracking-wide faint">
            What to do
          </h3>
          <ul className="space-y-2">
            {advice.actions.map((action) => (
              <li key={action.id} className="card flex gap-3 px-4 py-3.5">
                <span
                  className="mt-[7px] h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: PRIORITY_COLOUR[action.priority] }}
                  aria-hidden="true"
                />
                <span className="text-[16px]">
                  {action.text}
                  {action.when !== 'now' && (
                    <span className="ml-1.5 text-[13px] font-semibold uppercase tracking-wide faint">
                      {action.when}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {assessment && assessment.drivers.length > 0 && (
        <details className="card mb-5 px-4 py-3.5">
          <summary className="cursor-pointer font-semibold">Why this is different for you</summary>
          <ul className="mt-2.5 space-y-1.5 text-[16px]">
            {assessment.drivers.map((d) => (
              <li key={d.id} className="muted">
                {d.label}
              </li>
            ))}
          </ul>
          <p
            className="mt-3.5 border-t pt-3 text-[15px] muted"
            style={{ borderColor: 'var(--line)' }}
          >
            Comfortable for you is about {Math.round(assessment.thresholds.coldModerate)}° to{' '}
            {Math.round(assessment.thresholds.heatModerate)}°, against roughly 12° to 22° for
            someone with no added risks.
          </p>
        </details>
      )}

      <p className="text-[14px] faint">
        {fetchedAt && (
          <>
            Updated{' '}
            {new Date(fetchedAt).toLocaleTimeString('en-GB', {
              hour: '2-digit',
              minute: '2-digit',
            })}
            .{' '}
          </>
        )}
        Weather from Open-Meteo.
        {advice?.sources && ` Guidance based on ${advice.sources.join(' and ')}.`}
      </p>
      <p className="mt-2 text-[14px] faint">
        General guidance only — not medical advice. In an emergency call 999, or 111 for urgent
        advice.
      </p>
    </div>
  )
}
