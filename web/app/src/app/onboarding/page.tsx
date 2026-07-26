'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  Choice,
  FieldError,
  RadioChoice,
  Step,
  StepActions,
  StepProgress,
} from '@/components/ui'
import { newProfileId, saveProfile } from '@/lib/client-store'
import {
  DEMO_NHS_NUMBERS,
  factorsFromRecord,
  knownMedClasses,
  lookupRecord,
  type NhsRecord,
} from '@/lib/nhs'
import {
  ASPECT_OPTIONS,
  CHECKED_ON_OPTIONS,
  DWELLING_OPTIONS,
  FACTOR_GROUPS,
  factorLabel,
  type Aspect,
  type CheckedOn,
  type DwellingType,
  type Profile,
} from '@/lib/profile'
import { REGIONS, regionByCode } from '@/lib/regions'
import { assessRisk, bandLabel, BAND_COLOURS } from '@/lib/risk'
import type { RegionWeather } from '@/lib/weather'

/**
 * Onboarding.
 *
 * Shape: one question per screen, a visible "step N of 4", and a sticky action
 * bar so the primary button is always under a thumb. Nothing is mandatory
 * except a name and a location, because the people who most need this app are
 * the least likely to finish a long form.
 *
 * The location step reveals the live temperature for their region as soon as
 * the postcode resolves — the app demonstrates it works before asking for
 * anything personal, which is the point at which people decide to trust it.
 */

type StepId = 'intro' | 'nhs' | 'name' | 'location' | 'home' | 'factors' | 'checkedOn' | 'notes' | 'review'

/**
 * Only these four carry a "step N of 4" label — the intro and the review are
 * not questions, and counting them would make the form look longer than it is.
 */
const NUMBERED: StepId[] = ['name', 'location', 'home', 'factors', 'checkedOn', 'notes']

export default function OnboardingPage() {
  const router = useRouter()

  const [step, setStep] = useState<StepId>('intro')
  const [name, setName] = useState('')
  const [postcode, setPostcode] = useState('')
  const [regionCode, setRegionCode] = useState('')
  const [outward, setOutward] = useState('')
  const [placeName, setPlaceName] = useState('')
  const [factors, setFactors] = useState<string[]>([])
  const [medClasses, setMedClasses] = useState<string[]>([])
  const [dwellingType, setDwellingType] = useState<DwellingType>('house')
  const [floor, setFloor] = useState(0)
  const [aspect, setAspect] = useState<Aspect>('south')
  const [hasCooling, setHasCooling] = useState(false)
  const [checkedOn, setCheckedOn] = useState<CheckedOn>('sometimes')
  const [noneApply, setNoneApply] = useState(false)
  const [notes, setNotes] = useState('')

  // NHS record import. `imported` is kept after the step is left so the review
  // screen can say where the answers came from — a tick someone did not make
  // themselves should be attributed.
  const [nhsInput, setNhsInput] = useState('')
  const [nhsError, setNhsError] = useState<string | null>(null)
  const [found, setFound] = useState<NhsRecord | null>(null)
  const [imported, setImported] = useState<NhsRecord | null>(null)

  const [lookingUp, setLookingUp] = useState(false)
  const [lookupError, setLookupError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Weather for the chosen region, shown as reassurance on the location step.
  const [weather, setWeather] = useState<RegionWeather | null>(null)

  const stepRef = useRef<HTMLDivElement>(null)
  const anchorRef = useRef<HTMLDivElement>(null)

  /**
   * Focus management on step change.
   *
   * Two competing needs: a screen-reader user should be told they are on a new
   * question, and someone on a phone should be able to start typing without
   * hunting for the field. Focusing a wrapper satisfies the first but defeats
   * `autoFocus` on the input, which silently stops the on-screen keyboard from
   * opening — so prefer the step's own field, and fall back to the wrapper only
   * on steps that have none. The "Step N of 4" line is an aria-live region, so
   * the change is announced either way.
   */
  useEffect(() => {
    window.scrollTo({ top: 0 })

    const field = stepRef.current?.querySelector<HTMLElement>('[data-step-focus]')
    if (field) field.focus()
    else anchorRef.current?.focus()
  }, [step])

  const go = useCallback((to: StepId) => setStep(to), [])
  const stepIndex = NUMBERED.indexOf(step)

  async function lookupPostcode() {
    const trimmed = postcode.trim()
    if (trimmed.length < 5) return

    setLookingUp(true)
    setLookupError(null)
    setWeather(null)

    try {
      const res = await fetch(`/api/postcode?q=${encodeURIComponent(trimmed)}`)
      const body = await res.json()
      if (!res.ok) throw new Error(body.error ?? 'We could not check that postcode.')

      setRegionCode(body.regionCode)
      setOutward(body.outwardCode)
      setPlaceName(body.adminDistrict ?? body.regionName)
      void loadWeather(body.regionCode)
    } catch (e) {
      setLookupError((e as Error).message)
      setRegionCode('')
    } finally {
      setLookingUp(false)
    }
  }

  /** Best-effort: a missing temperature must not block onboarding. */
  const loadWeather = useCallback(async (code: string) => {
    try {
      const res = await fetch('/api/regions')
      if (!res.ok) return
      const body = await res.json()
      setWeather(body.regions.find((r: RegionWeather) => r.regionCode === code) ?? null)
    } catch {
      /* ignore */
    }
  }, [])

  function pickRegion(code: string) {
    setRegionCode(code)
    setOutward('')
    setPostcode('')
    setPlaceName(regionByCode(code)?.name ?? '')
    setLookupError(null)
    void loadWeather(code)
  }

  function findRecord() {
    const { record, error } = lookupRecord(nhsInput)
    setFound(record)
    setNhsError(error)
  }

  /**
   * Take the record's answers and carry on at the location step.
   *
   * The postcode is filled but still confirmed rather than accepted silently: a
   * record holds where someone is registered, which is not always where they
   * sleep, and the whole indoor model hangs off that address.
   */
  function useRecord(record: NhsRecord) {
    setImported(record)
    setName(record.name.split(' ')[0])
    setPostcode(record.postcode)
    setFactors(factorsFromRecord(record))
    setMedClasses(knownMedClasses(record))
    setNoneApply(false)
    go('location')
  }

  function toggleFactor(id: string) {
    setNoneApply(false)
    setFactors((prev) => (prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]))
  }

  const draft: Profile = {
    id: 'draft',
    name: name.trim() || 'You',
    regionCode,
    factors,
    createdAt: new Date().toISOString(),
  }

  async function finish() {
    setSaving(true)

    const profile: Profile = {
      id: newProfileId(),
      name: name.trim(),
      regionCode,
      postcodeOutward: outward || undefined,
      factors,
      medClasses: medClasses.length ? medClasses : undefined,
      home: { dwellingType, floor, aspect, hasCooling },
      checkedOn,
      notes: notes.trim() || undefined,
      createdAt: new Date().toISOString(),
    }

    // Save locally first — this is what signs the user in, so it must not
    // depend on the network call below succeeding.
    saveProfile(profile)

    try {
      await fetch('/api/profiles', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(profile),
      })
    } catch {
      /* Registering with the server is best-effort. */
    }

    router.push('/')
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-[34rem] flex-col px-5 pt-8">
      {/* Fallback focus target for steps with no input of their own. */}
      <div ref={anchorRef} tabIndex={-1} className="outline-none" />

      {stepIndex >= 0 && <StepProgress current={stepIndex + 1} total={NUMBERED.length} />}

      <div ref={stepRef} className="flex-1">
        {step === 'intro' && (
          <Step
            title="Let's get you set up"
            intro="Four short questions. There's no account and no password, and it takes about half a minute."
          >
            <ul className="space-y-3">
              {[
                {
                  title: 'Why we ask about your health',
                  body: 'The same weather is harmless for one person and dangerous for another. Knowing a little about you is what makes the advice yours.',
                },
                {
                  title: 'What we keep',
                  body: 'Your first name, your region, and what you tick. We keep only the first half of your postcode — enough to know your area, never your address.',
                },
                {
                  title: 'You can skip things',
                  body: 'Only your name and your area are needed. Everything else is optional and you can change it later.',
                },
              ].map((item) => (
                <li key={item.title} className="card p-4">
                  <p className="mb-1 font-semibold">{item.title}</p>
                  <p className="text-[16px] muted">{item.body}</p>
                </li>
              ))}
            </ul>
            <StepActions onNext={() => go('nhs')} nextLabel="Start" />
          </Step>
        )}

        {step === 'nhs' && (
          <Step
            title="Bring in your NHS record?"
            intro="It fills in your conditions and medicines so you don't have to remember them. You can type everything yourself instead."
          >
            <p
              className="mb-4 rounded-lg border px-3.5 py-2.5 text-[14px]"
              style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-soft)' }}
            >
              <strong>This is a demonstration.</strong> There is no real NHS
              connection here. Use one of the test numbers below to see how it would
              work.
            </p>

            <label htmlFor="nhs" className="mb-2 block font-medium">
              NHS number
            </label>
            <input
              id="nhs"
              data-step-focus
              value={nhsInput}
              onChange={(e) => {
                setNhsInput(e.target.value)
                setNhsError(null)
                setFound(null)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') findRecord()
              }}
              placeholder="999 000 0001"
              inputMode="numeric"
              enterKeyHint="search"
              className="field"
            />
            {nhsError && <FieldError>{nhsError}</FieldError>}

            <div className="mt-2 flex flex-wrap gap-1.5">
              {DEMO_NHS_NUMBERS.map((number) => (
                <button
                  key={number}
                  type="button"
                  className="btn btn-secondary"
                  style={{ minHeight: 'auto', padding: '0.35rem 0.6rem', fontSize: '13px' }}
                  onClick={() => {
                    setNhsInput(number)
                    setNhsError(null)
                    setFound(lookupRecord(number).record)
                  }}
                >
                  {number}
                </button>
              ))}
            </div>

            {!found && (
              <button type="button" className="btn btn-primary mt-4" onClick={findRecord}>
                Find my record
              </button>
            )}

            {found && (
              <div className="card mt-4 p-4">
                <p className="text-[11px] uppercase tracking-[0.14em] faint">
                  Record found
                </p>
                <p className="mt-1.5 text-[16px] font-semibold">{found.name}</p>
                <p className="text-[13.5px] muted">
                  {found.gpPractice} · {found.postcode} · updated {found.lastUpdated}
                </p>

                <dl className="mt-3 space-y-2 text-[14px]">
                  <div>
                    <dt className="text-[12px] faint">Conditions</dt>
                    <dd>
                      {found.conditions.length
                        ? found.conditions.map(factorLabel).join(' · ')
                        : 'None recorded'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[12px] faint">Repeat prescriptions</dt>
                    <dd>{found.medicines.length ? found.medicines.join(' · ') : 'None recorded'}</dd>
                  </div>
                </dl>

                {found.conditions.length === 0 && (
                  /* SC-7. An empty record is thin evidence, not evidence of safety,
                     and someone shown "nothing found" reads it as "I'm fine". */
                  <p className="mt-3 text-[13px] muted">
                    Nothing is coded on this record. That does not mean there is no
                    risk — age and housing matter too, so the next questions still
                    apply.
                  </p>
                )}

                <button
                  type="button"
                  className="btn btn-primary mt-4"
                  onClick={() => useRecord(found)}
                >
                  Use these details
                </button>
              </div>
            )}

            <StepActions
              onBack={() => go('intro')}
              onNext={() => go('name')}
              nextLabel="I'll type it myself"
            />
          </Step>
        )}

        {step === 'name' && (
          <Step
            title="What should we call you?"
            intro="Just a first name is fine — it's only used to greet you."
          >
            <label htmlFor="name" className="mb-2 block font-medium">
              First name
            </label>
            <input
              id="name"
              data-step-focus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && name.trim()) go('location')
              }}
              placeholder="e.g. Doris"
              autoComplete="given-name"
              enterKeyHint="next"
              className="field"
            />
            <StepActions
              onBack={() => go('nhs')}
              onNext={() => go('location')}
              nextDisabled={!name.trim()}
            />
          </Step>
        )}

        {step === 'location' && (
          <Step
            title="Whereabouts are you?"
            intro="Your postcode tells us which part of the UK to watch. We only store the first half of it."
          >
            <label htmlFor="postcode" className="mb-2 block font-medium">
              Postcode
            </label>
            <div className="flex gap-2.5">
              <input
                id="postcode"
                data-step-focus
                value={postcode}
                onChange={(e) => {
                  setPostcode(e.target.value)
                  setRegionCode('')
                  setWeather(null)
                  setLookupError(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void lookupPostcode()
                  }
                }}
                placeholder="e.g. B15 2TT"
                autoComplete="postal-code"
                autoCapitalize="characters"
                enterKeyHint="search"
                aria-invalid={Boolean(lookupError)}
                aria-describedby={lookupError ? 'postcode-error' : undefined}
                className={`field flex-1 uppercase ${lookupError ? 'field-invalid' : ''}`}
              />
              <button
                type="button"
                onClick={() => void lookupPostcode()}
                disabled={lookingUp || postcode.trim().length < 5}
                className="btn btn-secondary"
              >
                {lookingUp ? 'Checking…' : 'Check'}
              </button>
            </div>

            {lookupError && (
              <div id="postcode-error">
                <FieldError>{lookupError}</FieldError>
              </div>
            )}

            {/* The payoff: real data for their area, before they've committed
                to anything. This is what earns the next three taps. */}
            {regionCode && (
              <div
                className="fade-in mt-5 overflow-hidden rounded-[var(--radius-lg)] border"
                style={{ borderColor: 'var(--line)', background: 'var(--surface)' }}
              >
                <div className="flex items-center justify-between gap-4 p-4">
                  <div className="min-w-0">
                    <p className="text-[15px] font-medium faint">
                      {outward ? `${outward} — ${placeName}` : placeName}
                    </p>
                    <p className="text-[19px] font-semibold">
                      {regionByCode(regionCode)?.name}
                    </p>
                  </div>
                  {weather ? (
                    <div className="shrink-0 text-right">
                      <p className="text-[32px] font-bold leading-none">
                        {Math.round(weather.apparentTemperature)}°
                      </p>
                      <p className="text-[14px] faint">right now</p>
                    </div>
                  ) : (
                    <p className="shrink-0 text-[15px] faint">Loading…</p>
                  )}
                </div>
                <p
                  className="border-t px-4 py-2.5 text-[15px] muted"
                  style={{ borderColor: 'var(--line)' }}
                >
                  Found you. We&apos;ll watch this area for you.
                </p>
              </div>
            )}

            <details className="mt-6">
              <summary
                className="cursor-pointer py-2 text-[16px] font-medium"
                style={{ color: 'var(--accent)' }}
              >
                I&apos;d rather pick my area from a list
              </summary>
              <div className="mt-3 space-y-2">
                {REGIONS.map((r) => (
                  <RadioChoice
                    key={r.code}
                    label={r.name}
                    selected={regionCode === r.code}
                    onSelect={() => pickRegion(r.code)}
                  />
                ))}
              </div>
            </details>

            <StepActions
              onBack={() => go('name')}
              onNext={() => go('home')}
              nextDisabled={!regionCode}
              helper={regionCode ? undefined : 'Check a postcode, or pick your area from the list.'}
            />
          </Step>
        )}

        {step === 'home' && (
          <Step
            title="Tell us about your home"
            intro="How hot a bedroom gets overnight depends more on the building than on the forecast. These three answers change the estimate more than anything else you tell us."
          >
            <fieldset className="mb-5">
              <legend className="mb-2 font-medium">What kind of home is it?</legend>
              <div className="space-y-2">
                {DWELLING_OPTIONS.map((option) => (
                  <RadioChoice
                    key={option.id}
                    label={option.label}
                    selected={dwellingType === option.id}
                    onSelect={() => setDwellingType(option.id)}
                  />
                ))}
              </div>
            </fieldset>

            <fieldset className="mb-5">
              <legend className="mb-2 font-medium">Which floor do you sleep on?</legend>
              <div className="space-y-2">
                {[
                  { value: 0, label: 'Ground floor' },
                  { value: 1, label: 'First floor' },
                  { value: 2, label: 'Second floor or higher' },
                ].map((option) => (
                  <RadioChoice
                    key={option.value}
                    label={option.label}
                    selected={floor === option.value}
                    onSelect={() => setFloor(option.value)}
                  />
                ))}
              </div>
            </fieldset>

            <fieldset className="mb-5">
              <legend className="mb-2 font-medium">
                Which way does the bedroom window face?
              </legend>
              <p className="mb-2 text-[14px] muted">
                A rough guess is fine. If you are not sure, think about when the sun
                comes in.
              </p>
              <div className="space-y-2">
                {ASPECT_OPTIONS.map((option) => (
                  <Choice
                    key={option.id}
                    label={option.label}
                    hint={option.hint}
                    selected={aspect === option.id}
                    onToggle={() => setAspect(option.id)}
                  />
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="mb-2 font-medium">Anything to keep it cool?</legend>
              <Choice
                label="I have a fan, air conditioning, or a room that stays cool"
                hint="This changes the advice — without it, cooling the room early matters much more"
                selected={hasCooling}
                onToggle={() => setHasCooling(!hasCooling)}
              />
            </fieldset>

            <StepActions onBack={() => go('location')} onNext={() => go('factors')} />
          </Step>
        )}

        {step === 'factors' && (
          <Step
            title="Does anything here apply to you?"
            intro="This is what turns general weather advice into advice for you. Tick anything that applies — or say none of it does."
          >
            <div className="space-y-7">
              {FACTOR_GROUPS.map((group) => (
                <fieldset key={group.group}>
                  <legend className="mb-2.5 text-[15px] font-semibold uppercase tracking-wide faint">
                    {group.group}
                  </legend>
                  <div className="space-y-2">
                    {group.factors.map((factor) => (
                      <Choice
                        key={factor.id}
                        label={factor.label}
                        hint={factor.hint}
                        selected={factors.includes(factor.id)}
                        onToggle={() => toggleFactor(factor.id)}
                      />
                    ))}
                  </div>
                </fieldset>
              ))}

              {/* An explicit "none" is not the same as an untouched form — it
                  tells us they read the list, and it stops the review screen
                  looking broken. */}
              <Choice
                label="None of these apply to me"
                selected={noneApply}
                onToggle={() => {
                  setNoneApply((v) => !v)
                  setFactors([])
                }}
              />
            </div>

            <StepActions
              onBack={() => go('home')}
              onNext={() => go('checkedOn')}
              nextDisabled={factors.length === 0 && !noneApply}
              helper={
                factors.length === 0 && !noneApply
                  ? 'Tick what applies, or choose “None of these apply to me”.'
                  : undefined
              }
            />
          </Step>
        )}

        {step === 'checkedOn' && (
          <Step
            title="Does anyone check on you?"
            intro="This decides who we write to. If nobody does, we address the advice to you rather than to someone who is not there."
          >
            <div className="space-y-2">
              {CHECKED_ON_OPTIONS.map((option) => (
                <Choice
                  key={option.id}
                  label={option.label}
                  hint={option.hint}
                  selected={checkedOn === option.id}
                  onToggle={() => setCheckedOn(option.id)}
                />
              ))}
            </div>

            {checkedOn === 'nobody' && (
              <p className="mt-4 text-[14px] muted">
                Councils use this to find people who would otherwise be missed during a
                heat alert. It is the single most useful thing you can tell us.
              </p>
            )}

            <StepActions onBack={() => go('factors')} onNext={() => go('notes')} />
          </Step>
        )}

        {step === 'notes' && (
          <Step
            title="Anything else we should know?"
            intro="Optional — skip this if you like. It helps the assistant understand your situation."
          >
            <label htmlFor="notes" className="mb-2 block font-medium">
              In your own words
            </label>
            <textarea
              id="notes"
              data-step-focus
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              maxLength={500}
              placeholder="e.g. “I look after my mum next door” or “I cycle to work every day”"
              className="field resize-none"
            />
            <p className="mt-2 text-right text-[14px] faint">{notes.length}/500</p>

            <StepActions
              onBack={() => go('checkedOn')}
              onNext={() => go('review')}
              nextLabel={notes.trim() ? 'Continue' : 'Skip this'}
            />
          </Step>
        )}

        {step === 'review' && (
          <Step
            title={`All set, ${name.trim()}`}
            intro="Here's what we've got. Change anything that's not right."
          >
            <ReviewCard
              label="Your area"
              value={regionByCode(regionCode)?.name ?? regionCode}
              detail={outward ? `Postcode area ${outward}` : undefined}
              onEdit={() => go('location')}
            />

            <ReviewCard
              label="What applies to you"
              value={
                factors.length > 0
                  ? `${factors.length} thing${factors.length === 1 ? '' : 's'}`
                  : 'Nothing selected'
              }
              detail={factors.length > 0 ? factors.map(factorLabel).join(' · ') : undefined}
              onEdit={() => go('factors')}
            />

            {notes.trim() && (
              <ReviewCard label="Your note" value={notes.trim()} onEdit={() => go('notes')} />
            )}

            {/* Show the outcome, not just the inputs — it makes the point of
                the whole form obvious at the moment they finish it. */}
            {weather && regionCode && <BandPreview profile={draft} weather={weather} />}

            <StepActions
              onBack={() => go('notes')}
              onNext={finish}
              nextLabel="Finish"
              busy={saving}
            />
          </Step>
        )}
      </div>
    </main>
  )
}

function ReviewCard({
  label,
  value,
  detail,
  onEdit,
}: {
  label: string
  value: string
  detail?: string
  onEdit: () => void
}) {
  return (
    <div className="card mb-3 flex items-start justify-between gap-3 p-4">
      <div className="min-w-0">
        <p className="text-[15px] font-medium faint">{label}</p>
        <p className="font-semibold">{value}</p>
        {detail && <p className="mt-0.5 text-[15px] muted">{detail}</p>}
      </div>
      <button
        type="button"
        onClick={onEdit}
        className="btn btn-ghost shrink-0 px-3 py-1.5"
        style={{ minHeight: 'auto' }}
      >
        Change
      </button>
    </div>
  )
}

/** What their profile means today, computed with the real risk engine. */
function BandPreview({ profile, weather }: { profile: Profile; weather: RegionWeather }) {
  const assessment = assessRisk(profile, weather)
  const colour = BAND_COLOURS[assessment.band]

  return (
    <div
      className="mt-5 rounded-[var(--radius-lg)] p-4"
      style={{ background: `${colour}1f`, border: `1px solid ${colour}55` }}
    >
      <div className="flex items-center gap-2.5">
        <span
          className="h-3.5 w-3.5 shrink-0 rounded-full"
          style={{ background: colour }}
          aria-hidden="true"
        />
        <p className="font-semibold">Right now for you: {bandLabel(assessment.band)}</p>
      </div>
      <p className="mt-1.5 text-[16px] muted">
        It feels like {Math.round(weather.apparentTemperature)}° where you are. Comfortable for
        you is about {Math.round(assessment.thresholds.coldModerate)}° to{' '}
        {Math.round(assessment.thresholds.heatModerate)}°, against roughly 12° to 22° for
        someone with no added risks.
      </p>
    </div>
  )
}
