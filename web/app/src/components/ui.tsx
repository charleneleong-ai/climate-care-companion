'use client'

/**
 * Shared UI primitives.
 *
 * Deliberately small and unclever: every one of these is sized for a user who
 * may have shaky hands, poor near vision, or be using a screen reader — so tap
 * targets, labels and focus behaviour are baked in rather than left to each
 * call site to remember.
 */

import type { ReactNode } from 'react'

/** Tick icon used inside choice cards. */
export function CheckIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path
        d="M2 8L5.5 11.5L13 3.5"
        stroke="var(--paper)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * Progress along the flow.
 *
 * A labelled "Step 2 of 5" plus segment fills. The text matters more than the
 * bars — it is what a screen reader announces and what reassures someone that
 * the form is nearly over.
 */
export function StepProgress({ current, total }: { current: number; total: number }) {
  return (
    <div className="mb-7">
      <div className="mb-2.5 flex gap-1.5" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <div
            key={i}
            className="h-1.5 flex-1 rounded-full transition-colors duration-300"
            style={{ background: i < current ? 'var(--accent)' : 'var(--line)' }}
          />
        ))}
      </div>
      <p className="text-[15px] font-medium faint" role="status" aria-live="polite">
        Step {current} of {total}
      </p>
    </div>
  )
}

/**
 * One question per screen.
 *
 * `key`ing this on the step id restarts the enter animation, which gives a
 * sense of forward motion without a routing change.
 */
export function Step({
  title,
  intro,
  children,
}: {
  title: string
  intro?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="step-enter">
      <h1 className="mb-2.5 text-[28px] font-bold">{title}</h1>
      {intro && <div className="mb-7 text-[17px] muted">{intro}</div>}
      {children}
    </section>
  )
}

/** A tickable option. Renders a real checkbox for assistive tech. */
export function Choice({
  label,
  hint,
  selected,
  onToggle,
}: {
  label: string
  hint?: string
  selected: boolean
  onToggle: () => void
}) {
  return (
    <label className="choice" data-selected={selected}>
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        // Visually replaced by .choice-check, but kept in the accessibility
        // tree and focusable so keyboard and screen readers behave normally.
        className="sr-only"
      />
      <span className="choice-check" aria-hidden="true">
        <CheckIcon />
      </span>
      <span className="min-w-0">
        <span className="block font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-[15px] muted">{hint}</span>}
      </span>
    </label>
  )
}

/** Single-select variant, for picking one region from a list. */
export function RadioChoice({
  label,
  selected,
  onSelect,
}: {
  label: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className="choice"
      data-selected={selected}
    >
      <span
        className="choice-check"
        style={{ borderRadius: '999px' }}
        aria-hidden="true"
      >
        <CheckIcon />
      </span>
      <span className="font-medium">{label}</span>
    </button>
  )
}

/** Sticky action bar. Keeps the primary action reachable with one thumb. */
export function StepActions({
  onBack,
  onNext,
  nextLabel = 'Continue',
  nextDisabled,
  busy,
  helper,
}: {
  onBack?: () => void
  onNext: () => void
  nextLabel?: string
  nextDisabled?: boolean
  busy?: boolean
  helper?: string
}) {
  return (
    <div
      className="sticky bottom-0 z-10 mt-8"
      style={{
        // Solid, not a gradient. On a long list (the factors step) content
        // scrolls under this bar, and a translucent background left helper text
        // sitting illegibly on top of a card.
        background: 'var(--paper)',
        borderTop: '1px solid var(--line)',
        paddingTop: '0.875rem',
        paddingBottom: 'max(1rem, env(safe-area-inset-bottom))',
        // Bleed past the page's horizontal padding so the bar spans full width.
        marginLeft: '-1.25rem',
        marginRight: '-1.25rem',
        paddingLeft: '1.25rem',
        paddingRight: '1.25rem',
      }}
    >
      {helper && <p className="mb-2.5 text-center text-[15px] faint">{helper}</p>}
      <div className="flex gap-3">
        {onBack && (
          <button type="button" onClick={onBack} className="btn btn-secondary px-5">
            Back
          </button>
        )}
        <button
          type="button"
          onClick={onNext}
          disabled={nextDisabled || busy}
          className="btn btn-primary flex-1"
        >
          {busy ? 'Just a moment…' : nextLabel}
        </button>
      </div>
    </div>
  )
}

/** Inline error. Announced immediately, and never colour-only. */
export function FieldError({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="mt-3 flex items-start gap-2 text-[15px] font-medium"
      style={{ color: 'var(--danger)' }}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 18 18"
        fill="none"
        aria-hidden="true"
        className="mt-0.5 shrink-0"
      >
        <circle cx="9" cy="9" r="8" stroke="currentColor" strokeWidth="1.8" />
        <path d="M9 5v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="9" cy="12.75" r="1" fill="currentColor" />
      </svg>
      <span>{children}</span>
    </p>
  )
}
