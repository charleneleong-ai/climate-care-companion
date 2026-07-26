/**
 * Bringing in a health record.
 *
 * The product argument for this app is that risk is personal, and the honest
 * consequence is that it needs to know things — conditions, medicines, age. Asking
 * an 84-year-old to tick fifteen boxes on a phone is the point most of them stop.
 * A record they already have fills it in three seconds.
 *
 * SIMULATED. There is no NHS Login integration here and none is implied. Real
 * access runs through NHS Login (OIDC) for identity and the GP Connect or NHS App
 * APIs for the record itself, all of which require an organisation, a DSPT
 * submission and clinical safety sign-off (DCB0129). What this module does is
 * model the *shape* of that response, so the flow that consumes it is real even
 * though the source is not — and so the swap, when it comes, is one module.
 *
 * Every record here is fictional (SC-6). The demo NHS numbers use the 999 range
 * reserved for testing, which cannot belong to a real patient.
 */

import { MED_CLASS_OPTIONS } from '@/lib/clinical'

export interface NhsRecord {
  nhsNumber: string
  name: string
  /** As held on the record, not as the person describes themselves. */
  dateOfBirth: string
  postcode: string
  /** Coded conditions, already mapped to the factor ids the app scores on. */
  conditions: string[]
  /** Pharmacological classes from the repeat prescription list. */
  medClasses: string[]
  /** What the record calls each medicine, for showing back to the reader. */
  medicines: string[]
  gpPractice: string
  lastUpdated: string
}

/**
 * Test records, keyed by the NHS number someone types on the sign-in screen.
 *
 * Chosen to cover the three shapes of risk the scoring core distinguishes: a
 * frail person with an interacting prescription, a working-age person with a
 * single respiratory condition, and someone with nothing coded at all — who
 * matters because a record with no conditions must not read as "no risk".
 */
export const DEMO_RECORDS: Record<string, NhsRecord> = {
  '9990000001': {
    nhsNumber: '999 000 0001',
    name: 'Doris Whitfield',
    dateOfBirth: '1938-03-14',
    postcode: 'MK40 1AA',
    conditions: ['over85', 'cardiovascular', 'mobility', 'livesAlone'],
    medClasses: ['diuretic', 'beta_blocker'],
    medicines: ['Furosemide 40mg', 'Bisoprolol 2.5mg', 'Atorvastatin 20mg'],
    gpPractice: 'Kingsbrook Medical Centre',
    lastUpdated: '2026-06-02',
  },
  '9990000002': {
    nhsNumber: '999 000 0002',
    name: 'Marcus Adeyemi',
    dateOfBirth: '1991-11-02',
    postcode: 'E14 9GB',
    conditions: ['respiratory'],
    medClasses: [],
    medicines: ['Salbutamol inhaler', 'Beclometasone inhaler'],
    gpPractice: 'Poplar Health Partnership',
    lastUpdated: '2026-05-19',
  },
  '9990000003': {
    nhsNumber: '999 000 0003',
    name: 'Eileen Barnes',
    dateOfBirth: '1952-07-30',
    postcode: 'TR1 3XQ',
    conditions: ['over65', 'diabetes', 'renal', 'livesAlone'],
    medClasses: ['diuretic', 'ace_arb'],
    medicines: ['Indapamide 2.5mg', 'Ramipril 5mg', 'Metformin 500mg'],
    gpPractice: 'Truro Health Centre',
    lastUpdated: '2026-07-11',
  },
  '9990000004': {
    nhsNumber: '999 000 0004',
    name: 'Raymond Clarke',
    dateOfBirth: '1949-01-22',
    postcode: 'NE6 5TT',
    conditions: [],
    medClasses: [],
    medicines: [],
    gpPractice: 'Byker Primary Care',
    lastUpdated: '2026-02-08',
  },
}

export const DEMO_NHS_NUMBERS = Object.keys(DEMO_RECORDS)

/** Accepts the number with or without the spaces people naturally type. */
export function normaliseNhsNumber(input: string): string {
  return input.replace(/\D/g, '')
}

export interface NhsLookupResult {
  record: NhsRecord | null
  error: string | null
}

export function lookupRecord(input: string): NhsLookupResult {
  const digits = normaliseNhsNumber(input)
  if (digits.length !== 10) {
    return { record: null, error: 'An NHS number is 10 digits. Check and try again.' }
  }
  const record = DEMO_RECORDS[digits]
  if (!record) {
    // Deliberately does not say "no such patient" — in the real integration that
    // would leak whether a number is registered to anyone.
    return {
      record: null,
      error: 'We could not find a demo record for that number.',
    }
  }
  return { record, error: null }
}

export function ageFromDateOfBirth(dateOfBirth: string, today = new Date()): number {
  const born = new Date(dateOfBirth)
  let age = today.getFullYear() - born.getFullYear()
  const monthDelta = today.getMonth() - born.getMonth()
  if (monthDelta < 0 || (monthDelta === 0 && today.getDate() < born.getDate())) age -= 1
  return age
}

/**
 * Age bands the record implies, on top of anything coded.
 *
 * Derived rather than trusted: a record may code "over 65" and go stale, but a
 * date of birth does not. The bands are cumulative because the factor table
 * treats them as separate weights — someone of 87 is over 65 *and* over 85.
 */
export function ageFactors(dateOfBirth: string, today = new Date()): string[] {
  const age = ageFromDateOfBirth(dateOfBirth, today)
  return [
    ...(age >= 65 ? ['over65'] : []),
    ...(age >= 75 ? ['over75'] : []),
    ...(age >= 85 ? ['over85'] : []),
  ]
}

/**
 * What the record contributes to a profile, deduplicated and age-corrected.
 *
 * A repeat prescription also sets the `medication` factor, because the factor
 * list and the class list are scored separately — leaving it unticked would show
 * someone a profile that lists their water tablet and simultaneously says they
 * take nothing.
 */
export function factorsFromRecord(record: NhsRecord, today = new Date()): string[] {
  return [
    ...new Set([
      ...record.conditions,
      ...ageFactors(record.dateOfBirth, today),
      ...(knownMedClasses(record).length > 0 ? ['medication'] : []),
    ]),
  ]
}

const KNOWN_MED_CLASSES: ReadonlySet<string> = new Set<string>(
  MED_CLASS_OPTIONS.map((option) => option.id),
)

/**
 * Medicine classes the app recognises.
 *
 * Anything unmapped is dropped rather than guessed — an unrecognised class must
 * not become a silent zero-weight factor that looks like it was considered.
 * `unknownMedClasses` is the other half: a real integration will meet classes
 * this app has no rule for, and those need surfacing to whoever maintains the
 * interaction table, not swallowing.
 */
export function knownMedClasses(record: NhsRecord): string[] {
  return record.medClasses.filter((id) => KNOWN_MED_CLASSES.has(id))
}

export function unknownMedClasses(record: NhsRecord): string[] {
  return record.medClasses.filter((id) => !KNOWN_MED_CLASSES.has(id))
}
