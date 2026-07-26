'use client'

/**
 * The landing from a warning text.
 *
 * Someone tapped a link in an unsolicited health message. Two things have to
 * happen in the first screen or they close it: they need to know why it reached
 * them, and they need to see that the warning is real and general rather than a
 * claim about them personally. Only then is it reasonable to ask for anything.
 *
 * The area and the warning come in on the query string, put there by whoever sent
 * the message, so the page opens by repeating the thing the reader just read.
 * Arriving with nothing is a normal case — a forwarded link, a typed URL — and
 * falls back to the general version rather than an error.
 */

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

import AppShell from '@/components/AppShell'

const LEVEL_COPY: Record<string, { label: string; meaning: string }> = {
  yellow: {
    label: 'Yellow heat health alert',
    meaning:
      'Significant effects are likely for people who are especially vulnerable to heat, even though most people will be fine.',
  },
  amber: {
    label: 'Amber heat health alert',
    meaning:
      'Effects are likely across the whole population, and health services expect increased demand.',
  },
  red: {
    label: 'Red heat health alert',
    meaning:
      'A risk to life is expected across the population, not only for those already unwell.',
  },
}

function JoinContent() {
  const params = useSearchParams()
  const area = params.get('area') ?? 'your area'
  const level = (params.get('level') ?? 'amber').toLowerCase()
  const from = params.get('from')
  const alert = LEVEL_COPY[level] ?? LEVEL_COPY.amber

  return (
    <AppShell title={`Heat warning for ${area}`}>
      <section className="card p-5">
        <p className="text-[11px] uppercase tracking-[0.14em] faint">
          Why you got a message
        </p>
        <p className="mt-2 text-[16px]">
          <strong>{alert.label}</strong>
          {from ? ` from ${from}` : ''} covering {area}. {alert.meaning}
        </p>
        <p className="mt-3 text-[13.5px] muted">
          This warning is for everyone in the area. It does not say anything about
          your health — nothing is known about you yet.
        </p>
      </section>

      <h2 className="section-label mt-6">What this app adds</h2>
      <ul className="card">
        {[
          ['A warning is about a region. Risk is about a person.', 'Two people on the same street can face very different nights — it depends on age, health, medicines, and how hot the bedroom gets.'],
          ['It works out what to actually do.', 'Not "stay hydrated". Specific things, in an order, before the heat arrives.'],
          ['It tells someone else too.', 'If you look after someone, they get advice written for them and you get advice written for you.'],
        ].map(([heading, detail]) => (
          <li key={heading} className="row">
            <p className="text-[15px] font-semibold">{heading}</p>
            <p className="mt-1 text-[13.5px] muted">{detail}</p>
          </li>
        ))}
      </ul>

      <div className="mt-6 flex flex-col gap-2.5">
        <Link href={`/onboarding?area=${encodeURIComponent(area)}`} className="btn btn-primary">
          Set up — about 2 minutes
        </Link>
        <Link href="/companion" className="btn btn-secondary">
          I already have an account
        </Link>
      </div>

      <p className="mt-6 text-[12.5px] faint">
        You can bring in your NHS record to save answering questions, or type your
        details yourself. Either way nothing is shared with the sender of this
        message.
      </p>

      <p className="mt-4 text-[12px] faint">
        <strong>Demonstrator only.</strong> Not medical advice and not clinically
        validated.
      </p>
    </AppShell>
  )
}

export default function JoinPage() {
  // useSearchParams needs a Suspense boundary or the whole route opts out of
  // static rendering — and this is the one page that must open fast on a cold
  // 4G tap from a text message.
  return (
    <Suspense fallback={<AppShell title="Heat warning">{null}</AppShell>}>
      <JoinContent />
    </Suspense>
  )
}
