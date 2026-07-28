import type { Config } from 'tailwindcss'

export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Risk bands — used by both the map choropleth and the UI so a region
        // reads the same colour everywhere. See lib/risk.ts for the bands.
        band: {
          'cold-severe': '#2c5c8f',
          'cold-high': '#4e8fc4',
          'cold-mod': '#8fc2de',
          comfortable: '#7fb069',
          'heat-mod': '#f3c05a',
          'heat-high': '#e07a3f',
          'heat-severe': '#c1362f',
        },
      },
      fontFamily: {
        // CoolBuddy's pairing. System fonts stay as the fallback chain so a
        // failed webfont degrades to something legible rather than to serif
        // defaults — this audience cannot afford a broken-looking screen.
        sans: ['var(--font-ui)', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        prose: ['var(--font-prose)', 'ui-serif', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
