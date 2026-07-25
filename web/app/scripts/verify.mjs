/**
 * End-to-end check against live weather.
 *
 *   node scripts/verify.mjs [port]     (default 3000)
 *
 * The premise of the app is that the same weather produces different advice for
 * different people. That is what this verifies — not merely that endpoints
 * return 200.
 */

const PORT = process.argv[2] ?? '3000'
const BASE = `http://127.0.0.1:${PORT}`

const bar = (n) => '█'.repeat(Math.round(n / 5)).padEnd(20, '░')
const line = (c = '═') => c.repeat(76)

async function get(path) {
  const res = await fetch(BASE + path)
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(`${path} → ${res.status}: ${body.error ?? 'unknown error'}`)
  return body
}

// ── 1. The map data ────────────────────────────────────────────────────────
console.log(line())
console.log('UK REGIONAL CONDITIONS')
console.log(line())

const { regions, fetchedAt } = await get('/api/regions')
console.log(
  ['REGION'.padEnd(20), 'AIR'.padStart(7), 'FEELS'.padStart(7), 'BAND'.padStart(15)].join(''),
)
for (const r of regions) {
  console.log(
    r.regionName.padEnd(20) +
      `${r.temperature.toFixed(1)}°`.padStart(7) +
      `${r.apparentTemperature.toFixed(1)}°`.padStart(7) +
      r.band.padStart(15),
  )
}
const feels = regions.map((r) => r.apparentTemperature)
console.log(
  `\nSpread: ${(Math.max(...feels) - Math.min(...feels)).toFixed(1)}°C across the UK.  Updated ${fetchedAt}`,
)

// ── 2. Per-persona assessment and advice ───────────────────────────────────
const { results } = await get('/api/assess')

for (const r of results) {
  if (r.error) {
    console.error(`\n${r.profile}: ${r.error}`)
    continue
  }
  console.log('\n' + line())
  console.log(`${r.profile.name} — ${r.profile.region}`)
  console.log(line())
  console.log(
    `Conditions       ${r.conditions.temperature.toFixed(1)}°C air, feels like ${r.conditions.apparentTemperature.toFixed(1)}°C (${r.conditions.conditions})`,
  )
  console.log(`Their band       ${r.assessment.band} — ${r.assessment.bandLabel}`)
  console.log(`Severity         ${bar(r.assessment.severity)} ${r.assessment.severity}/100`)
  console.log(
    `Their comfort    ${r.assessment.thresholds.coldModerate.toFixed(0)}°C to ${r.assessment.thresholds.heatModerate.toFixed(0)}°C   (an average adult: 12°C to 22°C)`,
  )
  console.log(`Headroom         ${r.assessment.headroomToNextBand}°C to the next band`)
  console.log(`Worse later?     ${r.assessment.worseningToday ? 'YES' : 'no'}`)

  if (r.assessment.drivers.length) {
    console.log('\nWhy it is different for them:')
    for (const d of r.assessment.drivers) console.log(`   · ${d.label}`)
  }

  console.log(`\n▸ ${r.advice.headline}`)
  console.log(`  ${r.advice.summary}`)
  if (r.advice.urgentWarning) console.log(`  ⚠  ${r.advice.urgentWarning}`)
  console.log('\n  Actions:')
  for (const a of r.advice.actions) {
    const tag = a.priority === 'critical' ? '!!' : a.priority === 'important' ? ' !' : '  '
    console.log(`   ${tag} [${a.when.padEnd(7)}] ${a.text}`)
  }
}

// ── 3. Differentiation check ───────────────────────────────────────────────
console.log('\n' + line())
console.log('DIFFERENTIATION CHECK')
console.log(line())

const ok = results.filter((r) => !r.error)
for (const r of ok) {
  console.log(
    `  ${r.profile.name.padEnd(9)} ${r.assessment.band.padEnd(15)} sev ${String(r.assessment.severity).padStart(3)}   ${r.advice.actions.length} actions`,
  )
}

const bands = new Set(ok.map((r) => r.assessment.band))
const severities = new Set(ok.map((r) => r.assessment.severity))
const actionSets = new Set(ok.map((r) => r.advice.actions.map((a) => a.id).sort().join(',')))

console.log(
  `\n  ${bands.size} distinct bands · ${severities.size} distinct severities · ${actionSets.size} distinct action sets, across ${ok.length} personas.`,
)

const passed = actionSets.size > 1 && severities.size > 1
console.log(
  passed
    ? '  PASS — the same weather is producing genuinely different advice per person.'
    : '  FAIL — personas are getting identical results; personalisation is not working.',
)

// ── 4. Stress test at fixed temperatures ───────────────────────────────────
// Today's weather is whatever it is. A test that only passes when London
// happens to be hot is not a test — so drive every persona through the same
// fixed feels-like temperatures and check they diverge.
console.log('\n' + line())
console.log('STRESS TEST — every persona at the same feels-like temperature')
console.log(line())

const TEMPS = [-5, 2, 8, 17, 24, 28, 33]
const header = ['PERSONA'.padEnd(9), ...TEMPS.map((t) => `${t}°`.padStart(9))].join('')
console.log(header)

const grid = new Map()
for (const t of TEMPS) {
  const { results: r } = await get(`/api/assess?at=${t}`)
  for (const row of r.filter((x) => !x.error)) {
    if (!grid.has(row.profile.name)) grid.set(row.profile.name, [])
    grid.get(row.profile.name).push(row.assessment.band)
  }
}

const short = {
  'cold-severe': 'COLD!!',
  'cold-high': 'cold!',
  'cold-moderate': 'cold',
  comfortable: 'ok',
  'heat-moderate': 'warm',
  'heat-high': 'HOT!',
  'heat-severe': 'HOT!!',
}
for (const [name, bandsAtTemp] of grid) {
  console.log(name.padEnd(9) + bandsAtTemp.map((b) => short[b].padStart(9)).join(''))
}

// At a given temperature, different personas should not all agree — otherwise
// the profile is decorative.
let divergentColumns = 0
for (let i = 0; i < TEMPS.length; i++) {
  const column = new Set([...grid.values()].map((b) => b[i]))
  if (column.size > 1) divergentColumns++
}
console.log(
  `\n  ${divergentColumns} of ${TEMPS.length} temperatures produce different bands between personas.`,
)

// And the thresholds themselves must stay ordered for everyone — this is the
// invariant that the inverted-comfort-band bug violated.
const { results: ordered } = await get('/api/assess')
let orderingOk = true
for (const r of ordered.filter((x) => !x.error)) {
  const t = r.assessment.thresholds
  const seq = [t.coldSevere, t.coldHigh, t.coldModerate, t.heatModerate, t.heatHigh, t.heatSevere]
  const strictlyIncreasing = seq.every((v, i) => i === 0 || v > seq[i - 1])
  if (!strictlyIncreasing) {
    orderingOk = false
    console.log(`  BROKEN thresholds for ${r.profile.name}: ${seq.join(' < ')}`)
  }
}
console.log(
  orderingOk
    ? '  Thresholds strictly increasing for every persona (comfortable band intact).'
    : '  FAIL — inverted thresholds found.',
)

// ── 5. Postcode resolution ─────────────────────────────────────────────────
console.log('\n' + line())
console.log('POSTCODE → REGION')
console.log(line())
// Real postcodes, one per nation, plus two that must be rejected.
for (const pc of ['SW1A 1AA', 'NE1 7RU', 'IV2 3BW', 'CF10 1EP', 'BT1 5GS', 'ZZ1 1ZZ', 'nonsense']) {
  try {
    const r = await get(`/api/postcode?q=${encodeURIComponent(pc)}`)
    console.log(`  ${pc.padEnd(10)} → ${r.regionName} (${r.regionCode})`)
  } catch (e) {
    console.log(`  ${pc.padEnd(10)} → rejected: ${e.message.split(': ').pop()}`)
  }
}

const allPassed = passed && orderingOk && divergentColumns >= 2
console.log('\n' + line())
console.log(allPassed ? 'ALL CHECKS PASSED' : 'CHECKS FAILED')
console.log(line())
process.exit(allPassed ? 0 : 1)
