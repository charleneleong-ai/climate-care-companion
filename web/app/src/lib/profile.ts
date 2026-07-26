/**
 * Profiles. No passwords — onboarding collects a name, a location, and the
 * factors that actually change the advice. A stranger at a demo table can be
 * onboarded in about 30 seconds.
 */

/** Ids here must match the keys in FACTOR_SHIFTS in risk.ts. */
export const FACTOR_GROUPS: {
  group: string
  factors: { id: string; label: string; hint?: string }[]
}[] = [
  {
    group: 'About you',
    factors: [
      { id: 'over65', label: 'I am over 65' },
      { id: 'over75', label: 'I am over 75' },
      {
        id: 'over85',
        label: 'I am over 85',
        hint: 'This group had the highest heat-related death rate in England last summer',
      },
      { id: 'pregnant', label: 'I am pregnant' },
      { id: 'youngChild', label: 'There is a child under 5 in my home' },
      { id: 'livesAlone', label: 'I live alone' },
    ],
  },
  {
    group: 'Health',
    factors: [
      {
        id: 'respiratory',
        label: 'Respiratory condition',
        hint: 'Asthma, COPD, bronchitis',
      },
      {
        id: 'cardiovascular',
        label: 'Heart or circulatory condition',
        hint: 'Heart disease, high blood pressure, previous stroke',
      },
      { id: 'diabetes', label: 'Diabetes' },
      {
        id: 'renal',
        label: 'Kidney condition',
        hint: 'Reduced kidney function narrows the safe margin for fluids',
      },
      {
        id: 'dementia',
        label: 'Dementia or memory problems',
        hint: 'May not notice or report feeling too hot or too cold',
      },
      { id: 'mobility', label: 'Reduced mobility' },
      {
        id: 'medication',
        label: 'Medication affecting temperature',
        hint: 'Tick this, then say which — it changes the advice a lot',
      },
    ],
  },
  {
    group: 'Your home and routine',
    factors: [
      {
        id: 'coldHome',
        label: 'My home is hard or expensive to heat',
        hint: 'Draughty, poorly insulated, or you ration heating',
      },
      {
        id: 'overheatingHome',
        label: 'My home gets too hot',
        hint: 'Top floor, large south-facing windows, or poor ventilation',
      },
      {
        id: 'outdoorWork',
        label: 'I spend long periods outdoors',
        hint: 'Outdoor work, walking, or no car',
      },
    ],
  },
]

export const ALL_FACTOR_IDS = FACTOR_GROUPS.flatMap((g) => g.factors.map((f) => f.id))

export function factorLabel(id: string): string {
  for (const group of FACTOR_GROUPS) {
    const found = group.factors.find((f) => f.id === id)
    if (found) return found.label
  }
  return id
}

export type DwellingType = 'house' | 'flat' | 'bungalow' | 'care_home'
export type Aspect = 'north' | 'east' | 'south' | 'west'
export type CheckedOn = 'daily' | 'sometimes' | 'nobody'

export interface Home {
  dwellingType: DwellingType
  /** 0 = ground. Anything above the first floor is treated as top by FR-11. */
  floor: number
  /** Which way the main windows face — the single largest term in the offset. */
  aspect: Aspect
  /** Fan, air conditioning, or a room that reliably stays cool. */
  hasCooling: boolean
}

export const DWELLING_OPTIONS: { id: DwellingType; label: string; hint?: string }[] = [
  { id: 'house', label: 'A house' },
  { id: 'flat', label: 'A flat' },
  { id: 'bungalow', label: 'A bungalow' },
  { id: 'care_home', label: 'A care home' },
]

export const ASPECT_OPTIONS: { id: Aspect; label: string; hint?: string }[] = [
  { id: 'south', label: 'South', hint: 'Sun most of the day — the hottest' },
  { id: 'west', label: 'West', hint: 'Afternoon and evening sun' },
  { id: 'east', label: 'East', hint: 'Morning sun' },
  { id: 'north', label: 'North', hint: 'Little direct sun — the coolest' },
]

export const CHECKED_ON_OPTIONS: { id: CheckedOn; label: string; hint?: string }[] = [
  { id: 'daily', label: 'Yes, most days', hint: 'Family, a carer, or a neighbour' },
  { id: 'sometimes', label: 'Now and then' },
  {
    id: 'nobody',
    label: 'No one really',
    hint: 'We will write the advice to you directly rather than to someone else',
  },
]

export interface Profile {
  id: string
  name: string
  /** ONS ITL1 code of the person's region. */
  regionCode: string
  /** Optional — we only keep the outward code (e.g. "SW1A"), never the full postcode. */
  postcodeOutward?: string
  /** Vulnerability and context factors. Ids from ALL_FACTOR_IDS. */
  factors: string[]
  /**
   * Pharmacological classes, from MED_CLASS_OPTIONS in clinical.ts.
   *
   * Separate from `factors` because "on medication" is a yes/no and this is not:
   * lithium and a beta blocker are both a tick in the same box and a very
   * different risk. Optional so profiles saved before this existed still load.
   */
  medClasses?: string[]
  /**
   * The home, in the terms FR-11 models a bedroom with.
   *
   * Asked rather than assumed. The offsets span 2.8°C between a top-floor
   * south-facing flat and a ground-floor north-facing one — wider than the gap
   * between two tiers — so a guessed home does not give a slightly wrong answer,
   * it gives a different one. Optional so profiles saved before this existed
   * still load.
   */
  home?: Home
  /**
   * Whether anyone checks on them.
   *
   * Not a vulnerability weight — it decides who advice is addressed to and
   * whether a rise has anyone to notify. Someone with nobody is precisely who
   * the council view exists to find.
   */
  checkedOn?: CheckedOn
  /** Free text the assistant can use — "I look after my mum next door". */
  notes?: string
  createdAt: string
  /** True for the seeded demo personas, so they can be filtered out of real stats. */
  isDemo?: boolean
}

export function isValidProfile(p: unknown): p is Profile {
  if (!p || typeof p !== 'object') return false
  const c = p as Partial<Profile>
  return (
    typeof c.id === 'string' &&
    typeof c.name === 'string' &&
    c.name.trim().length > 0 &&
    typeof c.regionCode === 'string' &&
    Array.isArray(c.factors) &&
    c.factors.every((f) => typeof f === 'string') &&
    (c.medClasses === undefined ||
      (Array.isArray(c.medClasses) && c.medClasses.every((m) => typeof m === 'string')))
  )
}

/** Postcodes are stored as the outward code only — enough for a region, not a household. */
export function outwardCode(postcode: string): string {
  return postcode.trim().toUpperCase().replace(/\s+/g, '').slice(0, -3) || postcode.trim().toUpperCase()
}

/**
 * Demo personas.
 *
 * Organised around three arguments the demo makes:
 *
 *   Pair A — polypharmacy cascade (Alan vs Victor):
 *   The same cardiovascular diagnosis. Alan is on one drug; Victor is on four.
 *   Each drug adds a new interaction chain. Same GP letter, completely different plan.
 *
 *   Pair B — dormant condition activated by heat (Pat vs Doris):
 *   Both have dementia. Pat has no comorbidities or medications; Doris has COPD,
 *   polypharmacy, and no caregiver. The condition alone is not the risk.
 *
 *   Standalone C — advice contradiction (Sylvia):
 *   Her antipsychotic and anticholinergic switch off both the feeling of heat
 *   and sweating — so the generic NHS message ("your body will warn you")
 *   is factually wrong for her. The personalised watch-for inverts it explicitly.
 *
 *   Standalone D — low-score, high-stakes (Ben):
 *   Young, low vulnerability score. A risk number alone would skip him. But his
 *   insulin degrades above 25 °C — a life-critical storage failure that the
 *   interaction rules reach regardless of tier.
 */
export const DEMO_PROFILES: Profile[] = [
  // ── Pair A · Low end ─────────────────────────────────────────────────────
  {
    id: 'demo-alan',
    name: 'Alan',
    regionCode: 'TLH', // East of England — Bedford is TLH, not TLF
    postcodeOutward: 'MK40',
    factors: ['over65', 'cardiovascular'],
    medClasses: ['beta_blocker'],
    notes:
      'Cardiovascular disease, on bisoprolol. Lives with his daughter. ' +
      'Two interactions fire on a hot day: beta_blocker_exertion and cardiovascular_heat_load. ' +
      'Compare with Victor — same diagnosis, very different plan.',
    createdAt: '2026-07-25T09:00:00.000Z',
    isDemo: true,
  },
  // ── Pair A · High end ────────────────────────────────────────────────────
  {
    id: 'demo-victor',
    name: 'Victor',
    regionCode: 'TLH',
    postcodeOutward: 'MK40',
    factors: ['over75', 'livesAlone', 'cardiovascular', 'renal', 'respiratory', 'medication', 'overheatingHome'],
    medClasses: ['diuretic', 'ace_arb', 'beta_blocker', 'ssri'],
    notes:
      'Cardiovascular + renal + COPD, on furosemide, ramipril, bisoprolol and citalopram. Lives alone. ' +
      'Second-floor south-facing flat — does not cool below 24°C on hot nights. ' +
      'Eight interaction chains fire simultaneously. The generic "drink plenty" advice is wrong for him: ' +
      'renal_and_cardiovascular points the watch-for signs the opposite way to thirst. ' +
      'beta_blocker_exertion removes the cardiac warning that a gentle walk is dangerous.',
    createdAt: '2026-07-25T09:01:00.000Z',
    isDemo: true,
  },
  // ── Pair B · Low end ─────────────────────────────────────────────────────
  {
    id: 'demo-pat',
    name: 'Pat',
    regionCode: 'TLH',
    postcodeOutward: 'MK45',
    factors: ['over65', 'dementia'],
    medClasses: [],
    notes:
      'Early-onset dementia, no medications. Lives with her husband, has cooling, ground-floor bungalow. ' +
      'One interaction fires: dementia_cannot_self_report. She cannot tell you she is too hot, ' +
      'but she can move to a cooler room, and someone is watching. ' +
      'Compare with Doris — same condition, very different risk.',
    createdAt: '2026-07-25T09:02:00.000Z',
    isDemo: true,
  },
  // ── Pair B · High end ────────────────────────────────────────────────────
  {
    id: 'demo-doris',
    name: 'Doris',
    regionCode: 'TLH',
    postcodeOutward: 'MK40',
    factors: [
      'over85',
      'livesAlone',
      'dementia',
      'respiratory',
      'mobility',
      'medication',
      'overheatingHome',
    ],
    medClasses: ['diuretic', 'ace_arb', 'ssri'],
    notes:
      'Dementia + COPD, on furosemide, ramipril and sertraline. Lives alone, mobility limited, ' +
      'third-floor south-facing flat with no cooling. ' +
      'Five interaction chains fire: diuretic+ACE, SSRI hyponatraemia, respiratory heat, ' +
      'dementia self-report, and mobility cannot self-rescue — none of which she can recognise. ' +
      'The condition (dementia) is the same as Pat. The risk is not.',
    createdAt: '2026-07-25T09:03:00.000Z',
    isDemo: true,
  },
  // ── Standalone C — advice contradiction ──────────────────────────────────
  {
    id: 'demo-sylvia',
    name: 'Sylvia',
    regionCode: 'TLH',
    postcodeOutward: 'MK41',
    factors: ['over75', 'livesAlone', 'cardiovascular', 'mobility', 'medication', 'overheatingHome'],
    medClasses: ['antipsychotic', 'anticholinergic'],
    notes:
      'On olanzapine and oxybutynin. Lives alone, mobility limited, third-floor west flat — afternoon sun means it never cools below 25°C on hot nights. ' +
      'The NHS heat message says "your body will warn you — you will feel hot and start to sweat." ' +
      'For Sylvia both are switched off: olanzapine impairs temperature perception, ' +
      'oxybutynin suppresses sweating. anticholinergic_absent_sweating fires and states explicitly: ' +
      '"its absence is not reassurance." The caregiver must check the room — not ask how she feels.',
    createdAt: '2026-07-25T09:04:00.000Z',
    isDemo: true,
  },
  // ── Standalone D — low score, high stakes ────────────────────────────────
  {
    id: 'demo-ben',
    name: 'Ben',
    regionCode: 'TLH',
    postcodeOutward: 'MK44',
    factors: ['livesAlone', 'cardiovascular'],
    medClasses: ['heat_sensitive', 'ace_arb'],
    notes:
      'Type 1 diabetic, 61, on insulin glargine and lisinopril. ' +
      'Low vulnerability score — a risk number alone would skip him. ' +
      'But heat_sensitive_storage fires at tier Low regardless of age: ' +
      'insulin degrades above 25 °C and the failure arrives with no symptom until it is too late. ' +
      'diuretic_and_ace also fires: lisinopril blunts thirst so dehydration affecting ' +
      'insulin sensitivity goes unnoticed. Two interactions reached by following the person, not the tier.',
    createdAt: '2026-07-25T09:05:00.000Z',
    isDemo: true,
  },
  // ── Regional coverage ────────────────────────────────────────────────────
  // Marcus and Callum ensure the map shows activity in at least three regions.
  // They also demonstrate two scenarios the paired personas cannot:
  //   Marcus: the urban heat island and occupational exposure — the advice
  //           the system gives him on a hot day has nothing to do with age.
  //   Callum: cold risk dominates for most of the year. The same person who
  //           needs insulin storage advice in July needs cold-home advice in
  //           January. The risk engine handles both without a mode switch.
  {
    id: 'demo-marcus',
    name: 'Marcus',
    regionCode: 'TLI', // London — urban heat island, highest excess mortality risk at >29°C
    postcodeOutward: 'E14',
    factors: ['overheatingHome', 'outdoorWork', 'respiratory'],
    medClasses: [],
    notes:
      'Cycle courier, asthmatic. Eighth-floor east-facing flat — no cross-ventilation, never cools at night. ' +
      'On a hot day: hot air tightens the airways while the job keeps him outdoors through the peak. ' +
      'No polypharmacy, no old age — this is the occupational and environmental risk the vulnerability score misses.',
    createdAt: '2026-07-25T09:06:00.000Z',
    isDemo: true,
  },
  {
    id: 'demo-callum',
    name: 'Callum',
    regionCode: 'TLM', // Scotland — cold risk for most of the year; summer heat is a different problem
    postcodeOutward: 'IV2',
    factors: ['outdoorWork', 'diabetes'],
    medClasses: ['heat_sensitive'],
    notes:
      'Estate worker in the Highlands. Outdoors most of the day year round. Insulin-dependent diabetic. ' +
      'In winter: cold exposure and prolonged outdoor work are the risk. ' +
      'In summer: heat_sensitive_storage fires — insulin degrades above 25°C in a hot vehicle or kit bag. ' +
      'Same person, same system, different season, different plan.',
    createdAt: '2026-07-25T09:07:00.000Z',
    isDemo: true,
  },
]
