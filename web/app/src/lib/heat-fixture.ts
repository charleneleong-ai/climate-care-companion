/**
 * 19 July 2025 — Bedford / England heatwave fixture.
 *
 * Plausible regional apparent temperatures for that day based on Met Office
 * and UKHSA Episode 4 data. Used by the main map page and the /monitoring
 * dashboard so both show identical data.
 *
 * Overnight minimum: 17°C across England — no recovery window.
 * Peak apparent: 29°C in London, South East, and East of England (Bedford).
 */

import type { MapRegion } from '@/components/UKMap'
import { REGIONS } from '@/lib/regions'
import { assessRegionBaseline } from '@/lib/risk'
import type { RegionWeather } from '@/lib/weather'

/** Apparent temperature (°C) per ONS ITL1 region code on 19 July 2025. */
export const HEAT_TEMPS: Record<string, number> = {
  TLC: 23, // North East
  TLD: 24, // North West
  TLE: 25, // Yorkshire & Humber
  TLF: 28, // East Midlands
  TLG: 27, // West Midlands
  TLH: 29, // East of England — Bedford (the worked example)
  TLI: 29, // London
  TLJ: 29, // South East
  TLK: 26, // South West
  TLL: 24, // Wales
  TLM: 20, // Scotland
  TLN: 19, // Northern Ireland
}

export type HeatRegion = RegionWeather & MapRegion & { conditions: string }

/** All 12 UK regions with 19 July 2025 conditions pre-computed. */
export const HEAT_FIXTURE_REGIONS: HeatRegion[] = REGIONS.map((r) => {
  const temp = HEAT_TEMPS[r.code] ?? 22
  const weather: RegionWeather = {
    regionCode: r.code,
    regionName: r.name,
    temperature: temp,
    apparentTemperature: temp,
    humidity: 45,
    windSpeed: 10,
    weatherCode: 0, // clear sky
    todayMax: temp,
    todayMin: 17,
    todayApparentMax: temp,
    todayApparentMin: 17,
    observedAt: '2025-07-19T14:00:00Z',
  }
  return {
    ...weather,
    conditions: 'Clear sky',
    ...assessRegionBaseline(weather),
  }
})

export const HEAT_FIXTURE_META = {
  date: 'Saturday 19 July 2025',
  time: '14:00',
  location: 'England',
  peakTemp: 29,
  overnight: 17,
  spellDay: 3,
  alertLevel: 'None',
  excessDeaths: 146,
}
