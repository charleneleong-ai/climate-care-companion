import type { Metadata, Viewport } from 'next'
import { Newsreader, Signika } from 'next/font/google'

import ServiceWorker from '@/components/ServiceWorker'

import './globals.css'

// CoolBuddy's pairing: Signika carries the interface, Newsreader the sentences
// written in a human voice. `next/font` self-hosts both — a CDN link would put a
// render-blocking third party in front of advice someone opened because they
// were worried, and would fail outright on the offline path NFR-04 requires.
const signika = Signika({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-ui',
  display: 'swap',
})

const newsreader = Newsreader({
  subsets: ['latin'],
  weight: ['400', '500'],
  style: ['normal', 'italic'],
  variable: '--font-prose',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Climatise — UK heat and cold advice',
  description:
    'Personalised advice for staying safe when it is too hot or too cold, for every region of the UK.',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'Climatise',
    statusBarStyle: 'default',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // Installed PWAs should fill the screen on notched phones.
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f7f7f5' },
    { media: '(prefers-color-scheme: dark)', color: '#131311' },
  ],
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" className={`${signika.variable} ${newsreader.variable}`}>
      <body className="min-h-dvh">
        {children}
        <ServiceWorker />
      </body>
    </html>
  )
}
