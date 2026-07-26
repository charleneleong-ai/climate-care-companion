import { DEMO_RECORDS, factorsFromRecord, knownMedClasses, unknownMedClasses, lookupRecord, ageFromDateOfBirth } from '@/lib/nhs'
import { ALL_FACTOR_IDS } from '@/lib/profile'

const today = new Date('2026-07-25')
let bad = 0
for (const [num, r] of Object.entries(DEMO_RECORDS)) {
  const factors = factorsFromRecord(r, today)
  const unknownFactors = factors.filter((f) => !ALL_FACTOR_IDS.includes(f))
  const unknownMeds = unknownMedClasses(r)
  console.log(`${num}  ${r.name.padEnd(18)} age=${ageFromDateOfBirth(r.dateOfBirth, today)}`)
  console.log(`   factors: ${factors.join(', ') || '(none)'}`)
  console.log(`   meds   : ${knownMedClasses(r).join(', ') || '(none)'}`)
  if (unknownFactors.length) { console.log(`   ✗ UNKNOWN FACTOR IDS: ${unknownFactors}`); bad++ }
  if (unknownMeds.length) { console.log(`   ✗ UNMAPPED MED CLASSES: ${unknownMeds}`); bad++ }
}
console.log('\nlookup guards:')
console.log(' short   ->', lookupRecord('123').error)
console.log(' unknown ->', lookupRecord('9999999999').error)
console.log(' spaced  ->', lookupRecord('999 000 0001').record?.name)
console.log(bad === 0 ? '\nAll demo records map cleanly.' : `\n${bad} PROBLEM(S)`)
process.exit(bad === 0 ? 0 : 1)
