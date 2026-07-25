/**
 * The 12 UK ITL1 regions (formerly NUTS1) — the official ONS statistical
 * geography, and the same set `postcodes.io` resolves a postcode to.
 *
 * Codes and centroids come from the ONS ITL1_JAN_2025_UK_BUC boundary file,
 * the same source as public/data/uk-regions.geojson — so `code` joins the
 * weather data to the map polygons.
 */

export interface Region {
  /** ONS ITL1 code, e.g. "TLI". Joins to the GeoJSON `properties.code`. */
  code: string
  /** Display name, shortened from the ONS name for UI use. */
  name: string
  /** Full ONS name, kept so postcodes.io lookups can be matched back. */
  onsName: string
  /** Population-weighted centroid — the point we query weather for. */
  lat: number
  lon: number
}

export const REGIONS: Region[] = [
  { code: 'TLC', name: 'North East', onsName: 'North East (England)', lat: 55.0727, lon: -1.7304 },
  { code: 'TLD', name: 'North West', onsName: 'North West (England)', lat: 54.0643, lon: -2.7656 },
  { code: 'TLE', name: 'Yorkshire & Humber', onsName: 'Yorkshire and The Humber', lat: 53.906, lon: -1.1988 },
  { code: 'TLF', name: 'East Midlands', onsName: 'East Midlands (England)', lat: 52.7957, lon: -0.8484 },
  { code: 'TLG', name: 'West Midlands', onsName: 'West Midlands (England)', lat: 52.557, lon: -2.2036 },
  { code: 'TLH', name: 'East of England', onsName: 'East (England)', lat: 52.235, lon: 0.5063 },
  { code: 'TLI', name: 'London', onsName: 'London', lat: 51.4897, lon: -0.1345 },
  { code: 'TLJ', name: 'South East', onsName: 'South East (England)', lat: 51.451, lon: -0.9931 },
  { code: 'TLK', name: 'South West', onsName: 'South West (England)', lat: 51.053, lon: -2.949 },
  { code: 'TLL', name: 'Wales', onsName: 'Wales', lat: 52.4359, lon: -4.0109 },
  { code: 'TLM', name: 'Scotland', onsName: 'Scotland', lat: 56.1812, lon: -3.9703 },
  { code: 'TLN', name: 'Northern Ireland', onsName: 'Northern Ireland', lat: 54.615, lon: -6.8557 },
]

const BY_CODE = new Map(REGIONS.map((r) => [r.code, r]))

export function regionByCode(code: string): Region | undefined {
  return BY_CODE.get(code)
}

/**
 * Resolve a postcodes.io response to one of our 12 regions.
 *
 * postcodes.io returns `region` only for English postcodes — Scottish, Welsh
 * and NI postcodes have `region: null` and carry the nation in `country`
 * instead, so we fall back to that.
 */
export function regionFromPostcodeLookup(lookup: {
  region: string | null
  country: string | null
}): Region | undefined {
  const candidate = lookup.region ?? lookup.country
  if (!candidate) return undefined

  const needle = candidate.trim().toLowerCase()
  return REGIONS.find(
    (r) =>
      r.onsName.toLowerCase() === needle ||
      r.name.toLowerCase() === needle ||
      // ONS suffixes nations onto English region names ("North East (England)")
      // while postcodes.io does not ("North East").
      r.onsName.toLowerCase().replace(/\s*\(england\)$/, '') === needle,
  )
}
