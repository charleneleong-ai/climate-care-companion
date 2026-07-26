'use client'

/**
 * Alerts.
 *
 * The screen where the app stops being something you remember to open. Everything
 * else here is pull; this is the one place a person consents to being interrupted.
 *
 * Two things are shown that a settings screen normally would not:
 *   - Both messages, side by side. Someone agreeing to be messaged should see
 *     what their words will look like, and a caregiver should see that the person
 *     they look after is being told something gentler than they are.
 *   - What will not be sent. FR-22's six-hour limit and the upward-transition
 *     rule are the reason this is worth allowing, so they are stated rather than
 *     buried.
 */

import { useCallback, useEffect, useState } from 'react'

import AppShell from '@/components/AppShell'
import { loadProfile } from '@/lib/client-store'
import type { Profile } from '@/lib/profile'
import {
  currentPushState,
  disablePush,
  enablePush,
  isIos,
  isStandalone,
  type Audience,
  type PushState,
} from '@/lib/push'

const SAMPLE: Record<Audience, { who: (name: string) => string; body: (name: string) => string }> = {
  caregiver: {
    who: (name) => `To you, about ${name}`,
    body: (name) =>
      `${name}'s heat risk has risen to High for tonight. The most important thing to do: move their tablets off the windowsill — heat degrades some medicines. Open Climatise for the rest of the plan.`,
  },
  cared_for: {
    who: (name) => `To ${name}`,
    body: (name) =>
      `Hello ${name}. It is going to be hot tonight where you are. One thing that will help: keep a glass of water by your chair and drink from it often. If you feel unwell, tell someone straight away.`,
  },
}

export default function AlertsPage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [state, setState] = useState<PushState>('unsupported')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setProfile(loadProfile())
    void currentPushState().then(setState)
  }, [])

  const turnOn = useCallback(async () => {
    if (!profile) return
    setBusy(true)
    setError(null)
    try {
      setState(await enablePush({ personId: profile.id, audience: 'caregiver' }))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }, [profile])

  const turnOff = useCallback(async () => {
    setBusy(true)
    try {
      await disablePush()
      // Re-read rather than assuming: the browser permission stays granted, so
      // only the absence of a subscription distinguishes off from on.
      setState(await currentPushState())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }, [])

  const name = profile?.name ?? 'the person you look after'

  return (
    <AppShell title="Alerts">
      <section className="card p-5">
        <StatusRow state={state} busy={busy} onEnable={turnOn} onDisable={turnOff} />
        {error && (
          <p role="alert" className="mt-3 text-[14px]" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
        )}
      </section>

      <h2 className="section-label mt-6">What gets sent</h2>
      <p className="mb-2.5 text-[13.5px] muted">
        One heat warning produces two messages, written differently on purpose.
      </p>
      <div className="flex flex-col gap-2.5">
        {(['caregiver', 'cared_for'] as const).map((audience) => (
          <article key={audience} className="card p-4">
            <p className="text-[11px] uppercase tracking-[0.14em] faint">
              {SAMPLE[audience].who(name)}
            </p>
            <p className="mt-2 text-[15px]">{SAMPLE[audience].body(name)}</p>
          </article>
        ))}
      </div>
      <p className="mt-2.5 text-[12.5px] faint">
        Example wording. The action in each message is taken from {name}&rsquo;s
        prevention plan, so the real one depends on their conditions and medicines.
      </p>

      <h2 className="section-label mt-6">When it stays quiet</h2>
      <ul className="card">
        {[
          'Only when the risk goes up. Staying at the same level does not send again.',
          'At most one alert every six hours, however the weather moves.',
          'Never for Low risk. An alert that says nothing is wrong teaches people to ignore alerts.',
        ].map((line) => (
          <li key={line} className="row text-[14px] muted">
            {line}
          </li>
        ))}
      </ul>

      <p className="mt-8 text-[12px] faint">
        <strong>Demonstrator only.</strong> Not medical advice and not clinically
        validated.
      </p>
    </AppShell>
  )
}

function StatusRow({
  state,
  busy,
  onEnable,
  onDisable,
}: {
  state: PushState
  busy: boolean
  onEnable: () => void
  onDisable: () => void
}) {
  if (state === 'granted') {
    return (
      <>
        <p className="text-[16px] font-semibold">Alerts are on</p>
        <p className="mt-1.5 text-[14px] muted">
          This phone will be told when the risk rises, whether or not the app is open.
        </p>
        <button type="button" className="btn btn-secondary mt-4" disabled={busy} onClick={onDisable}>
          Turn off alerts
        </button>
      </>
    )
  }

  if (state === 'denied') {
    return (
      <>
        <p className="text-[16px] font-semibold">Alerts are blocked</p>
        {/* The browser will not re-prompt after a refusal, so pointing at the
            button again would be a dead end. Say where the switch actually is. */}
        <p className="mt-1.5 text-[14px] muted">
          This phone refused notifications earlier, and the app cannot ask again. Turn
          them back on in your browser or phone settings for Climatise.
        </p>
      </>
    )
  }

  if (state === 'needs-install') {
    return (
      <>
        <p className="text-[16px] font-semibold">Add Climatise to your home screen</p>
        <p className="mt-1.5 text-[14px] muted">
          On iPhone, alerts only work once the app is installed. Tap Share, then
          &ldquo;Add to Home Screen&rdquo;, and open Climatise from there.
        </p>
      </>
    )
  }

  if (state === 'unsupported') {
    return (
      <>
        <p className="text-[16px] font-semibold">This browser cannot receive alerts</p>
        <p className="mt-1.5 text-[14px] muted">
          {isIos() && !isStandalone()
            ? 'Add Climatise to your home screen and open it from there.'
            : 'Everything else works — you will need to open the app to check.'}
        </p>
      </>
    )
  }

  return (
    <>
      <p className="text-[16px] font-semibold">Get told before it gets dangerous</p>
      <p className="mt-1.5 text-[14px] muted">
        Without this, someone has to remember to open the app on the evening they are
        least likely to think of it.
      </p>
      <button type="button" className="btn btn-primary mt-4" disabled={busy} onClick={onEnable}>
        {busy ? 'Turning on…' : 'Turn on alerts'}
      </button>
    </>
  )
}
