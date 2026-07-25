/**
 * Open-Meteo client. No API key, no rate-limit signup, generous free tier —
 * which is why it beat the Met Office DataPoint API for a hackathon build.
 *
 * One batched request covers all 12 regions: Open-Meteo accepts
 * comma-separated latitude/longitude lists and returns a parallel array.
 */

import { REGIONS, type Region } from './regions'

export interface RegionWeather {
  regionCode: string
  regionName: string
  /** Dry-bulb air temperature, °C. */
  temperature: number
  /** "Feels like" — factors in wind chill and humidity. What advice keys off. */
  apparentTemperature: number
  humidity: number
  /** km/h */
  windSpeed: number
  /** WMO weather interpretation code. */
  weatherCode: number
  /** Today's forecast range, for "it'll get colder tonight" style advice. */
  todayMax: number
  todayMin: number
  todayApparentMax: number
  todayApparentMin: number
  observedAt: string
}

export interface WeatherSnapshot {
  regions: RegionWeather[]
  fetchedAt: string
}

const CURRENT_FIELDS = [
  'temperature_2m',
  'apparent_temperature',
  'relative_humidity_2m',
  'wind_speed_10m',
  'weather_code',
].join(',')

const DAILY_FIELDS = [
  'temperature_2m_max',
  'temperature_2m_min',
  'apparent_temperature_max',
  'apparent_temperature_min',
].join(',')

/** Shape of one entry in Open-Meteo's multi-location response. */
interface OpenMeteoLocation {
  current: {
    time: string
    temperature_2m: number
    apparent_temperature: number
    relative_humidity_2m: number
    wind_speed_10m: number
    weather_code: number
  }
  daily: {
    temperature_2m_max: number[]
    temperature_2m_min: number[]
    apparent_temperature_max: number[]
    apparent_temperature_min: number[]
  }
}

function buildUrl(regions: Region[]): string {
  const params = new URLSearchParams({
    latitude: regions.map((r) => r.lat).join(','),
    longitude: regions.map((r) => r.lon).join(','),
    current: CURRENT_FIELDS,
    daily: DAILY_FIELDS,
    timezone: 'Europe/London',
    forecast_days: '2',
  })
  return `https://api.open-meteo.com/v1/forecast?${params}`
}

/**
 * Fetch current conditions for all 12 UK regions in one request.
 *
 * Cached for 10 minutes: Open-Meteo updates on a 15-minute cadence, so a
 * shorter TTL just burns quota without producing fresher numbers.
 */
export async function fetchAllRegions(): Promise<WeatherSnapshot> {
  const res = await fetch(buildUrl(REGIONS), {
    next: { revalidate: 600 },
  })

  if (!res.ok) {
    throw new Error(`Open-Meteo returned ${res.status} ${res.statusText}`)
  }

  const body = await res.json()

  // Open-Meteo returns a bare object for a single location and an array for
  // many. We always request 12, but normalise so a one-region call can reuse
  // this parser.
  const locations: OpenMeteoLocation[] = Array.isArray(body) ? body : [body]

  if (locations.length !== REGIONS.length) {
    throw new Error(
      `Expected ${REGIONS.length} locations from Open-Meteo, got ${locations.length}`,
    )
  }

  return {
    regions: REGIONS.map((region, i) => {
      const loc = locations[i]
      return {
        regionCode: region.code,
        regionName: region.name,
        temperature: loc.current.temperature_2m,
        apparentTemperature: loc.current.apparent_temperature,
        humidity: loc.current.relative_humidity_2m,
        windSpeed: loc.current.wind_speed_10m,
        weatherCode: loc.current.weather_code,
        todayMax: loc.daily.temperature_2m_max[0],
        todayMin: loc.daily.temperature_2m_min[0],
        todayApparentMax: loc.daily.apparent_temperature_max[0],
        todayApparentMin: loc.daily.apparent_temperature_min[0],
        observedAt: loc.current.time,
      }
    }),
    fetchedAt: new Date().toISOString(),
  }
}

/** WMO code → short human label. Covers the codes the UK actually sees. */
export function describeWeatherCode(code: number): string {
  if (code === 0) return 'Clear sky'
  if (code <= 2) return 'Partly cloudy'
  if (code === 3) return 'Overcast'
  if (code === 45 || code === 48) return 'Fog'
  if (code >= 51 && code <= 57) return 'Drizzle'
  if (code >= 61 && code <= 67) return 'Rain'
  if (code >= 71 && code <= 77) return 'Snow'
  if (code >= 80 && code <= 82) return 'Rain showers'
  if (code === 85 || code === 86) return 'Snow showers'
  if (code >= 95) return 'Thunderstorm'
  return 'Unsettled'
}
