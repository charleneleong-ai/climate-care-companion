import type { Metadata, Viewport } from 'next'

import ServiceWorker from '@/components/ServiceWorker'

import './globals.css'

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
    <html lang="en-GB">
      <body className="min-h-dvh">
        {children}
        <ServiceWorker />
      </body>
    </html>
  )
}
