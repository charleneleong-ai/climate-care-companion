'use client'

/**
 * App chrome.
 *
 * The difference between a page and an app is not the technology — the PWA was
 * installable before this existed. It is that an app has a fixed place to stand:
 * a bar that does not scroll away, a title that stays put, and somewhere to
 * return to. On a page, a caregiver who scrolls past the tier has lost it.
 *
 * Three things are load-bearing rather than decorative:
 *   - `env(safe-area-inset-*)`, because an installed app draws under the notch
 *     and under the home indicator, and a tap target beneath the indicator
 *     cannot be hit.
 *   - 48px minimum on every tab, matching --tap. NFR-06, and the reason the
 *     labels are short.
 *   - The active tab is marked by weight and a rule as well as colour (NFR-07),
 *     so it survives a greyscale screen and a colour-blind reader.
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

interface Tab {
  href: string
  label: string
  glyph: ReactNode
}

const TABS: Tab[] = [
  {
    href: '/companion',
    label: 'Today',
    glyph: (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-6 w-6">
        <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
        <g stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
          <path d="M12 3v2.4M12 18.6V21M3 12h2.4M18.6 12H21" />
          <path d="M5.6 5.6l1.7 1.7M16.7 16.7l1.7 1.7M18.4 5.6l-1.7 1.7M7.3 16.7l-1.7 1.7" />
        </g>
      </svg>
    ),
  },
  {
    href: '/alerts',
    label: 'Alerts',
    glyph: (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-6 w-6">
        <path
          d="M6.2 10.2a5.8 5.8 0 1 1 11.6 0c0 3.4.9 5 1.8 6H4.4c.9-1 1.8-2.6 1.8-6Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinejoin="round"
        />
        <path
          d="M10 19.2a2.2 2.2 0 0 0 4 0"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    href: '/onboarding',
    label: 'Profile',
    glyph: (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-6 w-6">
        <circle cx="12" cy="8.4" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.7" />
        <path
          d="M4.8 20c.7-3.7 3.7-5.8 7.2-5.8s6.5 2.1 7.2 5.8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
]

export default function AppShell({
  title,
  trailing,
  children,
}: {
  title: string
  trailing?: ReactNode
  children: ReactNode
}) {
  const pathname = usePathname()

  return (
    <div className="app-shell">
      <header className="app-bar">
        <div className="app-bar-inner">
          <div>
            <p className="app-eyebrow">Climatise</p>
            <h1 className="app-title">{title}</h1>
          </div>
          {trailing}
        </div>
      </header>

      <div className="app-body">{children}</div>

      <nav className="app-tabs" aria-label="Sections">
        {TABS.map((tab) => {
          const active = pathname === tab.href
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? 'page' : undefined}
              className={`app-tab${active ? ' is-active' : ''}`}
            >
              {tab.glyph}
              <span>{tab.label}</span>
            </Link>
          )
        })}
      </nav>
    </div>
  )
}
