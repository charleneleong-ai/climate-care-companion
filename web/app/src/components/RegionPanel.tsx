'use client'

import {
  ESCALATION,
  SOURCE_LABEL,
  TIER,
  type AssessmentResult,
} from '@/lib/assessment'
import type { Profile } from '@/lib/profile'
import { regionByCode } from '@/lib/regions'
import { BAND_COLOURS, bandLabel, type RiskBand } from '@/lib/risk'
import type { RegionWeather } from '@/lib/weather'

interface Props {
  profile: Profile
  region: (RegionWeather & { conditions: string; band: RiskBand; severity: number }) | null
  /** Advice is only personalised for the user's own region. */
  isOwnRegion: boolean
  fetchedAt: string | null
  /** The core's answer for this person. Null while it loads, or if it failed —
   *  the panel then shows the region's conditions and says nothing about them. */
  assessment: AssessmentResult | null
  /** Showing a cached answer. Said out loud rather than passed off as fresh. */
  stale: boolean
  failed: boolean
}

export default function RegionPanel({
  profile,
  region,
  isOwnRegion,
  fetchedAt,
  assessment,
  stale,
  failed,
}: Props) {
  if (!region) {
    return (
      <div className="px-5 py-6 text-[16px] muted">
        Tap a region on the map to see its conditions.
      </div>
    )
  }

  const regionName = regionByCode(region.regionCode)?.name ?? region.regionCode

  // For the user's own region we show their personal assessment; elsewhere we
  // show the region's own conditions without pretending the advice applies to
  // them somewhere they aren't.
  const mine = isOwnRegion ? assessment : null
  const displayBand = mine?.assessment.band ?? region.band
  const bandColour = BAND_COLOURS[displayBand]
  const plan = mine?.plan
  // Reserved for the tier that means "this could kill them tonight". Below it
  // the same box in the same red would only teach people to ignore red.
  const severe = mine?.assessment.tier === 'Severe'

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
          <p className="font-semibold">{bandLabel(displayBand)}</p>
        </div>
        {mine ? (
          <p className="mt-1.5 text-[16px]">{TIER[mine.assessment.tier].act.cared_for}</p>
        ) : (
          <p className="mt-1.5 text-[16px] muted">
            Today {Math.round(region.todayMin)}° to {Math.round(region.todayMax)}°. This is how it
            feels for an average adult — your own advice is for{' '}
            {regionByCode(profile.regionCode)?.name}.
          </p>
        )}
      </div>

      {/* An assessment that could not be reached is a fact to report. Silence
          here reads as "nothing to worry about", which is the one meaning it
          must never carry. */}
      {isOwnRegion && failed && !assessment && (
        <p className="mb-5 text-[16px]" style={{ color: 'var(--danger)' }}>
          Your personal assessment could not be reached, so this shows the region&rsquo;s
          conditions only. Nothing here is about you specifically.
        </p>
      )}

      {plan && plan.watch_points.length > 0 && (
        <div
          role={severe ? 'alert' : undefined}
          className="mb-5 rounded-[var(--radius-lg)] px-4 py-3.5 text-[16px]"
          style={
            severe
              ? { background: 'var(--danger-wash)', border: '2px solid var(--danger)' }
              : { background: 'var(--surface)', border: '1px solid var(--line-strong)' }
          }
        >
          <strong className="mb-1 block" style={severe ? { color: 'var(--danger)' } : undefined}>
            {severe ? 'Get help if you see this' : 'Worth keeping an eye out for'}
          </strong>
          <ul className="space-y-1">
            {plan.watch_points.map((point, i) => (
              <li key={`${i}-${point}`}>{point}</li>
            ))}
          </ul>
          {severe && (
            <p className="mt-2 font-semibold" style={{ color: 'var(--danger)' }}>
              If you see any of these, call 999.
            </p>
          )}
        </div>
      )}

      {plan && plan.items.length > 0 && (
        <section className="mb-5">
          <h3 className="mb-2.5 text-[15px] font-semibold uppercase tracking-wide faint">
            What to do
          </h3>
          <ul className="space-y-2">
            {plan.items.map((item) => (
              <li key={item.code} className="card flex gap-3 px-4 py-3.5">
                <span
                  className="mt-[7px] h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{
                    background: item.escalate_to ? 'var(--danger)' : 'var(--line-strong)',
                  }}
                  aria-hidden="true"
                />
                <span className="prose-voice">
                  {item.text}
                  {(item.escalate_to || SOURCE_LABEL[item.source]) && (
                    <span className="ml-1.5 text-[13px] font-semibold uppercase tracking-wide faint">
                      {item.escalate_to
                        ? (ESCALATION[item.escalate_to] ?? item.escalate_to)
                        : SOURCE_LABEL[item.source]}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {plan && plan.escalate_to.length > 0 && (
        <section className="mb-5">
          <h3 className="mb-2.5 text-[15px] font-semibold uppercase tracking-wide faint">
            If this is not enough
          </h3>
          <ul className="space-y-2">
            {plan.escalate_to.map((who) => (
              <li key={who} className="card px-4 py-3 text-[16px]">
                {ESCALATION[who] ?? who}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* `open` by default: these reasons are the answer to the question the
          product exists to answer, so collapsing them by default asks the
          reader to go looking for the one thing that makes the tier mean
          anything. Still collapsible, for a reader who has already read it. */}
      {mine && mine.assessment.reasons.length > 0 && (
        <details open className="card mb-5 px-4 py-3.5">
          <summary className="cursor-pointer font-semibold">Why this is different for you</summary>
          <ul className="mt-2.5 space-y-2 text-[16px]">
            {mine.assessment.reasons.map((reason) => (
              <li key={reason.code}>
                <span className="font-medium">{reason.title}</span>
                <span className="prose-voice muted"> — {reason.explanation}</span>
              </li>
            ))}
          </ul>
          {/* SC-5: modelled, and said so at the point of display. */}
          <p
            className="mt-3.5 border-t pt-3 text-[15px] muted"
            style={{ borderColor: 'var(--line)' }}
          >
            Your bedroom overnight is modelled at about{' '}
            {mine.assessment.indoorNightEstimateModelled.toFixed(1)}°, estimated from the forecast
            and your home rather than measured.
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
        {mine && ` Assessment from the Climatise core (${mine.assessment.source}).`}
        {mine &&
          stale &&
          (failed
            ? ' Showing the last saved answer — the refresh did not get through.'
            : ' Showing the last saved answer while it refreshes.')}
      </p>
      <p className="mt-2 text-[14px] faint">
        General guidance only — not medical advice. In an emergency call 999, or 111 for urgent
        advice.
      </p>
    </div>
  )
}
