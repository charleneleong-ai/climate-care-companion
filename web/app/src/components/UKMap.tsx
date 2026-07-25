'use client'

import 'leaflet/dist/leaflet.css'

import type { GeoJsonObject } from 'geojson'
import L from 'leaflet'
import { useCallback, useEffect, useRef, useState } from 'react'

import { BAND_COLOURS, type RiskBand } from '@/lib/risk'

/**
 * Whole-UK choropleth, coloured by risk band.
 *
 * Renders the ONS boundary polygons with **no tile layer**: it loads instantly,
 * needs no external tile requests or attribution, works offline once the
 * GeoJSON is cached, and reads as a data visualisation rather than a street
 * map — which is what this is.
 *
 * Drives Leaflet directly rather than through react-leaflet. react-leaflet v4's
 * `MapContainer` does not survive React StrictMode's deliberate
 * mount/unmount/remount in development: it leaves Leaflet's `_leaflet_id` on
 * the container and the second mount throws "Map container is already
 * initialized". Owning the lifecycle here means one explicit `map.remove()` in
 * cleanup fixes it, and the imperative fit/resize logic below was already
 * reaching around react-leaflet anyway.
 */

/** Latitude above which boundary geometry is excluded from the initial fit. */
const NORTH_FIT_LIMIT = 59

export interface MapRegion {
  regionCode: string
  regionName: string
  temperature: number
  apparentTemperature: number
  band: RiskBand
  severity: number
}

interface Props {
  regions: MapRegion[]
  /** The viewer's own region — outlined heavily so they can find themselves. */
  myRegionCode?: string
  selectedRegionCode?: string
  onSelectRegion: (regionCode: string) => void
}

export default function UKMap({
  regions,
  myRegionCode,
  selectedRegionCode,
  onSelectRegion,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.GeoJSON | null>(null)

  const [geo, setGeo] = useState<GeoJsonObject | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Handlers and props read inside Leaflet callbacks live in refs, so the map
  // is built once and never has to be torn down to pick up a new prop.
  const selectRef = useRef(onSelectRegion)
  selectRef.current = onSelectRegion

  const propsRef = useRef({ regions, myRegionCode, selectedRegionCode })
  propsRef.current = { regions, myRegionCode, selectedRegionCode }

  // ── Load boundaries ─────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    fetch('/data/uk-regions.geojson')
      .then((r) => {
        if (!r.ok) throw new Error(`boundaries returned ${r.status}`)
        return r.json()
      })
      .then((data) => {
        if (!cancelled) setGeo(data)
      })
      .catch((e) => {
        console.error('[UKMap] failed to load boundaries', e)
        if (!cancelled) setError('Could not load the map outlines.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const styleFor = useCallback((code: string | undefined): L.PathOptions => {
    const { regions: rs, myRegionCode: mine, selectedRegionCode: selected } = propsRef.current
    const region = code ? rs.find((r) => r.regionCode === code) : undefined
    const isMine = code === mine
    const isSelected = code === selected

    return {
      fillColor: region ? BAND_COLOURS[region.band] : '#c9c8c4',
      fillOpacity: isSelected ? 0.95 : 0.72,
      weight: isMine ? 3 : isSelected ? 2.5 : 1,
      color: isMine ? '#191814' : '#ffffff',
      opacity: 1,
    }
  }, [])

  /**
   * Fit the view to the boundary extent so the UK fills the frame at any
   * viewport size, then keep it fitted as the container changes.
   */
  const refit = useCallback(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return

    map.invalidateSize({ animate: false })

    const bounds = layer.getBounds()
    if (!bounds.isValid()) return

    // Clip the far northern isles out of the *fit* (they still render).
    // Shetland sits near 60.9°N, a few hundred km past the mainland, and
    // including it stretches the vertical extent enough to visibly shrink the
    // regions people actually tap.
    const north = Math.min(bounds.getNorth(), NORTH_FIT_LIMIT)

    map.fitBounds(
      L.latLngBounds([bounds.getSouth(), bounds.getWest()], [north, bounds.getEast()]),
      { padding: [6, 6], animate: false },
    )
  }, [])

  // ── Build the map once boundaries are in ────────────────────────────────
  useEffect(() => {
    const container = containerRef.current
    if (!container || !geo) return

    const map = L.map(container, {
      center: [54.6, -3.4],
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
      // Panning a full-bleed map on a phone fights page scrolling; this map is
      // for tapping regions, not for navigating.
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      touchZoom: false,
      keyboard: false,
      // Leaflet's default grey would show through where there is no polygon.
      // The wrapper supplies the background instead.
      zoomAnimation: false,
    })
    mapRef.current = map

    const layer = L.geoJSON(geo, {
      style: (feature) => styleFor(feature?.properties?.code),
      onEachFeature: (feature, lyr) => {
        const code = feature?.properties?.code as string | undefined
        if (!code) return

        lyr.on('click', () => selectRef.current(code))
        lyr.on('keydown', (e: L.LeafletKeyboardEvent) => {
          if (e.originalEvent.key === 'Enter' || e.originalEvent.key === ' ') {
            e.originalEvent.preventDefault()
            selectRef.current(code)
          }
        })
      },
    }).addTo(map)
    layerRef.current = layer

    // Two frames: one for layout to settle, one for Leaflet to see the size.
    const raf = requestAnimationFrame(() => requestAnimationFrame(refit))
    const observer = new ResizeObserver(refit)
    observer.observe(container)

    return () => {
      cancelAnimationFrame(raf)
      observer.disconnect()
      // The line that makes StrictMode's double-mount safe: without it the
      // container keeps its _leaflet_id and the remount throws.
      map.remove()
      mapRef.current = null
      layerRef.current = null
    }
  }, [geo, refit, styleFor])

  // ── Restyle in place when data or selection changes ─────────────────────
  useEffect(() => {
    const layer = layerRef.current
    if (!layer) return

    layer.eachLayer((lyr) => {
      const feature = (lyr as L.GeoJSON & { feature?: GeoJSON.Feature }).feature
      const code = feature?.properties?.code as string | undefined
      if (!code) return

      const path = lyr as L.Path
      path.setStyle(styleFor(code))

      const region = regions.find((r) => r.regionCode === code)
      const name = (feature?.properties?.name as string | undefined) ?? code

      // Tooltips carry live temperatures, so they are rebound on each update.
      lyr.unbindTooltip()
      if (region) {
        lyr.bindTooltip(
          `<strong>${region.regionName}</strong><br>Feels like ${Math.round(
            region.apparentTemperature,
          )}°C`,
          { sticky: true, direction: 'top', opacity: 1 },
        )
      }

      const el = (path as L.Path & { getElement?: () => Element | undefined }).getElement?.()
      if (el) {
        el.classList.add('climatise-region')
        // Keyboard and screen-reader access to a Leaflet vector layer.
        el.setAttribute('tabindex', '0')
        el.setAttribute('role', 'button')
        el.setAttribute(
          'aria-label',
          region
            ? `${region.regionName}: feels like ${Math.round(region.apparentTemperature)} degrees`
            : name,
        )
        el.setAttribute('aria-pressed', String(code === selectedRegionCode))
      }
    })
  }, [regions, myRegionCode, selectedRegionCode, styleFor])

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-[15px] faint">
        {error}
      </div>
    )
  }

  return <div ref={containerRef} className="h-full w-full" style={{ background: 'transparent' }} />
}
