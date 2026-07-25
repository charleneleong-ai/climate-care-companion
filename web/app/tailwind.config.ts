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
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
