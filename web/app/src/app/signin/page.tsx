'use client'

/**
 * Signing in as one of the seeded people.
 *
 * There are no accounts in this demonstrator, so "I already have an account"
 * would otherwise land on an empty companion screen — a dead end in the middle
 * of a demo. This offers the register instead.
 *
 * Everything shown afterwards is a live assessment against real weather; only
 * the person is fictional (SC-6). That distinction is stated on screen rather
 * than left for the reader to assume, because a screen that looks like a real
 * patient record should say when it is not one.
 */

import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

import AppShell from '@/components/AppShell'
import { signInAsPersona } from '@/lib/client-store'

interface Persona {
  id: string
  name: string
  ageBand: string
  ageLabel: string
}

export default function SignInPage() {
  const router = useRouter()
  const [people, setPeople] = useState<Persona[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/personas')
      .then(async (response) => {
        const body = await response.json()
        if (!response.ok) throw new Error(body.error ?? 'Could not load the register.')
        setPeople(body.people)
      })
      .catch((e) => setError((e as Error).message))
  }, [])

  const choose = useCallback(
    (persona: Persona) => {
      signInAsPersona(persona.id, persona.name)
      router.push('/companion')
    },
    [router],
  )

  return (
    <AppShell title="Who are you looking after?">
      <p
        className="mb-4 rounded-lg border px-3.5 py-2.5 text-[14px]"
        style={{ borderColor: 'var(--line-strong)', color: 'var(--ink-soft)' }}
      >
        <strong>Demonstration people.</strong> These are fictional. The weather and
        the risk assessment behind each one are real and live.
      </p>

      {error && (
        <p role="alert" className="text-[15px]" style={{ color: 'var(--danger)' }}>
          {error}
        </p>
      )}

      {!people && !error && <p className="text-[15px] muted">Loading the register…</p>}

      <div className="card">
        {people?.map((persona) => (
          <button
            key={persona.id}
            type="button"
            onClick={() => choose(persona)}
            className="row flex w-full items-center justify-between gap-3 text-left"
            style={{ minHeight: 'var(--tap)' }}
          >
            <span>
              <span className="block text-[16px] font-semibold">{persona.name}</span>
              <span className="block text-[13px] faint">{persona.ageLabel}</span>
            </span>
            <span aria-hidden="true" className="text-[18px] faint">
              →
            </span>
          </button>
        ))}
      </div>

      <p className="mt-6 text-[13px] muted">
        Setting up as yourself instead?{' '}
        <a href="/onboarding" className="underline">
          Answer a few questions
        </a>{' '}
        and the same assessment runs against your own postcode and home.
      </p>
    </AppShell>
  )
}
