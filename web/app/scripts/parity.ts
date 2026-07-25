/**
 * Run the Python parity corpus against the TypeScript risk model.
 *
 *     npx tsx scripts/parity.ts
 *
 * ────────────────────────────────────────────────────────────────────────────
 *  This is the test that tells you whether the two models can be reconciled at
 *  all. Everything before it proved the *content* matches — the same medication
 *  weights, the same interaction rules. This asks the harder question: given the
 *  same person in the same weather, do they reach the same conclusion?
 *
 *  It is expected to fail in places. A parity harness that passes on day one is
 *  usually measuring nothing.
 * ────────────────────────────────────────────────────────────────────────────
 *
 * The mapping is the honest part. The two models do not share an input type:
 *
 *   Python takes ExposureFeatures — a modelled indoor night and day figure, a
 *   spell-day counter, and outdoor peaks.
 *   TypeScript takes RegionWeather — a current apparent temperature, humidity,
 *   wind, and today's range.
 *
 * `indoor_night_est`, `indoor_day_est` and `spell_day` have no TypeScript
 * equivalent at all, so the corpus cannot simply be replayed. Each field is
 * mapped below with a comment saying what is lost. Where a disagreement traces
 * to a lost field rather than to the models, the report says so.
 */

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Profile } from '../src/lib/profile'
import { assessRisk, bandRank, type RiskBand } from '../src/lib/risk'
import type { RegionWeather } from '../src/lib/weather'

const HERE = dirname(fileURLToPath(import.meta.url))
const CORPUS = join(HERE, '..', '..', 'shared', 'parity-corpus.generated.json')

type Tier = 'Low' | 'Elevated' | 'High' | 'Severe'
const TIER_RANK: Record<Tier, number> = { Low: 0, Elevated: 1, High: 2, Severe: 3 }

const TIER_FOR_BAND: Record<RiskBand, Tier> = {
  comfortable: 'Low',
  'cold-moderate': 'Elevated',
  'heat-moderate': 'Elevated',
  'cold-high': 'High',
  'heat-high': 'High',
  'cold-severe': 'Severe',
  'heat-severe': 'Severe',
}

interface Case {
  name: string
  exposure: {
    overnight_min: number
    peak_apparent: number
    peak_air: number
    indoor_night_est: number
    indoor_day_est: number
    spell_day: number
  }
  person: {
    age_band: string
    lives_alone: boolean
    mobility_limited: boolean
    conditions: string[]
    med_classes: string[]
  }
  expected: {
    tier: Tier
    risk_score: number
    exposure_score: number
    vulnerability_score: number
    codes: string[]
  }
}

/**
 * Age bands do not line up. Python has an 85+ band carrying the heaviest age
 * weight in the specification; the TypeScript stops at "over 75", so an
 * 88-year-old and a 76-year-old are indistinguishable to it.
 */
const AGE_FACTORS: Record<string, string[]> = {
  under_65: [],
  b65_74: ['over65'],
  b75_84: ['over75'],
  b85_plus: ['over75'], // LOSS: the 85+ distinction has nowhere to go
}

const CONDITION_FACTORS: Record<string, string> = {
  dementia: 'dementia',
  cardiovascular: 'cardiovascular',
  renal: 'renal',
  respiratory: 'respiratory',
}

function toProfile(c: Case): Profile {
  const factors = [
    ...AGE_FACTORS[c.person.age_band],
    ...(c.person.lives_alone ? ['livesAlone'] : []),
    ...(c.person.mobility_limited ? ['mobility'] : []),
    ...c.person.conditions.map((k) => CONDITION_FACTORS[k]).filter(Boolean),
  ]
  return {
    id: 'parity',
    name: 'Parity case',
    regionCode: 'TLI',
    factors,
    medClasses: c.person.med_classes,
    createdAt: '2026-07-25T00:00:00Z',
  }
}

function toWeather(c: Case): RegionWeather {
  return {
    regionCode: 'TLI',
    regionName: 'Parity',
    // The fairest single number: the hottest this person will feel today. The
    // Python bands on a modelled indoor figure, which has no equivalent here.
    temperature: c.exposure.peak_air,
    apparentTemperature: c.exposure.peak_apparent,
    // Neutral, so neither adds a driver the corpus never specified.
    humidity: 50,
    windSpeed: 5,
    weatherCode: 0,
    todayMax: c.exposure.peak_air,
    todayMin: c.exposure.overnight_min,
    todayApparentMax: c.exposure.peak_apparent,
    todayApparentMin: c.exposure.overnight_min,
    observedAt: '2026-07-25T12:00',
  } as RegionWeather
}

/** Fields the corpus carries that the TypeScript model cannot represent. */
function lostFields(c: Case): string[] {
  const lost: string[] = []
  if (c.exposure.spell_day > 0) lost.push(`spell_day=${c.exposure.spell_day}`)
  lost.push(`indoor_night=${c.exposure.indoor_night_est}`)
  lost.push(`indoor_day=${c.exposure.indoor_day_est}`)
  if (c.person.age_band === 'b85_plus') lost.push('age 85+ → over75')
  return lost
}

const corpus = JSON.parse(readFileSync(CORPUS, 'utf8')) as { cases: Case[] }

let agreed = 0
let disagreed = 0
const rows: string[] = []

for (const c of corpus.cases) {
  const assessment = assessRisk(toProfile(c), toWeather(c))
  const got = TIER_FOR_BAND[assessment.band]
  const want = c.expected.tier
  const match = got === want
  match ? agreed++ : disagreed++

  const direction =
    TIER_RANK[got] > TIER_RANK[want] ? 'over' : TIER_RANK[got] < TIER_RANK[want] ? 'UNDER' : '—'

  rows.push(
    [
      match ? '  ok  ' : '  XX  ',
      c.name.padEnd(38),
      `py=${want}`.padEnd(14),
      `ts=${got}`.padEnd(14),
      `(${assessment.band}, sev ${assessment.severity})`.padEnd(28),
      direction,
    ].join(''),
  )
  if (!match) {
    rows.push(`        lost in translation: ${lostFields(c).join(', ')}`)
  }
}

console.log('\nPARITY: Python corpus vs TypeScript risk model\n')
console.log(rows.join('\n'))
console.log(`\n  ${agreed} agree, ${disagreed} disagree, of ${corpus.cases.length}\n`)

if (disagreed > 0) {
  console.log(
    '  A disagreement is not automatically a bug. The models band on different\n' +
      '  quantities — Python on a modelled indoor temperature, TypeScript on\n' +
      '  outdoor apparent — so some divergence is structural and is the thing\n' +
      '  docs/reconciliation.md says has to be decided rather than patched.\n' +
      '  What matters is whether TypeScript ever lands UNDER Python: banding a\n' +
      '  person safer than the core does is the failure SC-7 forbids.\n',
  )
}

const underCount = corpus.cases.filter((c) => {
  const got = TIER_FOR_BAND[assessRisk(toProfile(c), toWeather(c)).band]
  return TIER_RANK[got] < TIER_RANK[c.expected.tier]
}).length

void bandRank


// ─── Comfortable window ─────────────────────────────────────────────────────
//
// The comparison that means something. A tier and a band are different labels
// for different quantities; a boundary *temperature* is the same quantity in
// both, and the gap is measurable in degrees.

interface Sweep {
  name: string
  person: Case['person']
  vulnerability_score: number
  comfortable_from: number | null
  comfortable_to: number | null
  heat_boundaries: Record<string, number>
  cold_boundaries: Record<string, number>
}

const sweeps = (JSON.parse(readFileSync(CORPUS, 'utf8')) as { sweeps: Sweep[] }).sweeps

function tsWindow(person: Case['person']): { from: number | null; to: number | null } {
  const profile = toProfile({ person } as Case)
  const comfortable: number[] = []
  for (let temperature = -10; temperature <= 45; temperature++) {
    const weather = {
      regionCode: 'TLI', regionName: 'Parity',
      temperature, apparentTemperature: temperature,
      humidity: 50, windSpeed: 5, weatherCode: 0,
      todayMax: temperature, todayMin: temperature - 8,
      todayApparentMax: temperature, todayApparentMin: temperature - 8,
      observedAt: '2026-07-25T12:00',
    } as RegionWeather
    if (assessRisk(profile, weather).band === 'comfortable') comfortable.push(temperature)
  }
  return comfortable.length
    ? { from: comfortable[0], to: comfortable[comfortable.length - 1] }
    : { from: null, to: null }
}

console.log('\nCOMFORTABLE WINDOW — the outdoor range each model calls Low/comfortable\n')
console.log(
  '  ' + 'vuln'.padEnd(6) + 'python'.padEnd(14) + 'typescript'.padEnd(14) + 'cold edge   heat edge',
)

const seen = new Set<string>()
for (const sweep of sweeps) {
  const key = JSON.stringify(sweep.person)
  if (seen.has(key)) continue
  seen.add(key)

  const ts = tsWindow(sweep.person)
  const py = `${sweep.comfortable_from}..${sweep.comfortable_to}°C`
  const tsw = ts.from === null ? 'never' : `${ts.from}..${ts.to}°C`
  const coldGap = ts.from !== null && sweep.comfortable_from !== null
    ? ts.from - sweep.comfortable_from : NaN
  const heatGap = ts.to !== null && sweep.comfortable_to !== null
    ? ts.to - sweep.comfortable_to : NaN

  console.log(
    '  ' + String(sweep.vulnerability_score).padEnd(6) + py.padEnd(14) + tsw.padEnd(14) +
      `${coldGap >= 0 ? '+' : ''}${coldGap}°C`.padEnd(12) +
      `${heatGap >= 0 ? '+' : ''}${heatGap}°C` +
      (heatGap > 0 ? '  ← TS tolerates more heat' : ''),
  )
}

console.log(
  '\n  The finding is the shape, not the gap.\n\n' +
  '  Python puts every person\'s window at the same place: vulnerability never\n' +
  '  moves it, because exposure alone decides whether there is any risk and\n' +
  '  vulnerability only multiplies what is already there (spec 8.4, FR-18).\n\n' +
  '  TypeScript moves the window per person: a frail person becomes at-risk at a\n' +
  '  temperature a healthy one does not (spec 1.3, "a personal threshold").\n\n' +
  '  Both are in the brief and they contradict each other. No amount of shared\n' +
  '  data reconciles that — it is a decision. See docs/reconciliation.md.\n',
)

if (underCount > 0) {
  console.error(
    `  UNSAFE: ${underCount} corpus case(s) band under the Python tier.\n` +
      '  Under-warning is the failure SC-7 names as dominant.\n',
  )
  process.exit(1)
}
