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
 * Five demo personas that prove the concept: same weather, five different
 * pieces of advice. Deliberately spread across regions and risk directions
 * so a demo shows contrast whatever the actual UK weather is on the day.
 */
export const DEMO_PROFILES: Profile[] = [
  {
    id: 'demo-doris',
    name: 'Doris',
    regionCode: 'TLC', // North East — usually the cold end of the country
    postcodeOutward: 'NE6',
    factors: ['over85', 'livesAlone', 'cardiovascular', 'coldHome', 'mobility'],
    notes:
      'Retired, lives alone in a Victorian terrace. Worries about the heating bill and tends to sit in one room.',
    createdAt: '2026-07-25T09:00:00.000Z',
    isDemo: true,
  },
  {
    id: 'demo-marcus',
    name: 'Marcus',
    regionCode: 'TLI', // London — the hot end, and urban heat island
    postcodeOutward: 'E14',
    factors: ['overheatingHome', 'outdoorWork', 'respiratory'],
    notes:
      'Cycle courier, asthmatic. Eighth-floor flat with windows on one side only, so it never cools down at night.',
    createdAt: '2026-07-25T09:01:00.000Z',
    isDemo: true,
  },
  {
    id: 'demo-priya',
    name: 'Priya',
    regionCode: 'TLG', // West Midlands
    postcodeOutward: 'B15',
    factors: ['pregnant', 'youngChild'],
    notes: 'Seven months pregnant with a three-year-old. Walks the school run twice a day.',
    createdAt: '2026-07-25T09:02:00.000Z',
    isDemo: true,
  },
  {
    id: 'demo-callum',
    name: 'Callum',
    regionCode: 'TLM', // Scotland
    postcodeOutward: 'IV2',
    factors: ['outdoorWork', 'diabetes'],
    notes: 'Estate worker in the Highlands, outdoors most of the day year round.',
    createdAt: '2026-07-25T09:03:00.000Z',
    isDemo: true,
  },
  {
    id: 'demo-eileen',
    name: 'Eileen',
    regionCode: 'TLK', // South West
    postcodeOutward: 'TR1',
    factors: ['over65', 'medication', 'diabetes', 'livesAlone'],
    medClasses: ['diuretic', 'beta_blocker'],
    notes:
      'Takes a diuretic and a beta-blocker, so she dehydrates quickly and does not feel heat building up.',
    createdAt: '2026-07-25T09:04:00.000Z',
    isDemo: true,
  },
]
