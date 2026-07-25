/**
 * Clinical content, generated from the Python core.
 *
 * ────────────────────────────────────────────────────────────────────────────
 *  Do not edit the JSON this imports. Regenerate it:
 *      uv run python -m core.export
 *  A stale copy fails the Python build via tests/verification/test_generated_freshness.
 * ────────────────────────────────────────────────────────────────────────────
 *
 * Why this exists. `risk.ts` bands on temperature, which it does well. It has no
 * way to express two things the specification treats as central:
 *
 *  1. **Which** medicine. A single "on medication" checkbox cannot distinguish
 *     lithium — where dehydration concentrates it and the safe range is narrow,
 *     making it the heaviest single vulnerability in the brief — from a beta
 *     blocker. The architecture reference calls medication the differentiator.
 *
 *  2. **Combinations.** Heat plus reduced kidney function plus a water tablet is
 *     a different instruction from any of the three alone, and for renal plus
 *     cardiovascular the usual "drink plenty in hot weather" advice is actively
 *     dangerous. That cannot be a sum of factors.
 *
 * It is imported rather than fetched deliberately: the app has to work offline,
 * and clinical content should not be the first thing to vanish when it does.
 */

import generated from '@/generated/clinical.generated.json'

export type MedClassId =
  | 'diuretic'
  | 'anticholinergic'
  | 'beta_blocker'
  | 'ace_arb'
  | 'antipsychotic'
  | 'ssri'
  | 'lithium'
  | 'heat_sensitive'

export interface InteractionRule {
  code: string
  /** Fires only at or above this outdoor peak, in °C. Null means no heat bound. */
  min_peak_air: number | null
  /** Fires only at or below this indoor day estimate. Null means no cold bound. */
  max_indoor_day: number | null
  requires_conditions: string[]
  requires_med_classes: string[]
  /** Boolean attributes on the person — mobility_limited, lives_alone. */
  requires_flags: string[]
  /**
   * Gates the rule on something the person actually told us.
   *
   * Null for everything except the self-report rules. Those must never fire
   * without an answer: "You said your bedroom feels too hot" attributed to
   * someone who said nothing of the kind is worse than saying nothing.
   */
  requires_self_report: { field: string; expected: boolean } | null
  min_tier: 'Low' | 'Elevated' | 'High' | 'Severe'
  advice_caregiver: string
  /** Null where the instruction is not one the person can act on themselves. */
  advice_person: string | null
  watch_for: string | null
  escalate_to: string | null
  supersedes: string[]
}

/** Drug name → class. Used to classify a free-text medicine list. */
export const MED_CLASSES: Record<string, string> = generated.med_classes

/**
 * Class → vulnerability weight, straight from spec §8.2.
 *
 * Lithium 3, diuretic/anticholinergic/antipsychotic 2, the rest 1. These are the
 * numbers the checkbox was flattening.
 */
export const MED_CLASS_WEIGHTS: Record<string, number> = generated.med_class_weights

export const INTERACTIONS: InteractionRule[] = generated.interactions as InteractionRule[]

/** What the onboarding form offers. Ordered heaviest-first so the ones that
 *  matter most are not buried at the bottom of the list. */
export const MED_CLASS_OPTIONS: {
  id: MedClassId
  label: string
  hint: string
}[] = [
  {
    id: 'lithium',
    label: 'Lithium',
    hint: 'Dehydration concentrates it, and the safe range is narrow',
  },
  {
    id: 'diuretic',
    label: 'A water tablet (diuretic)',
    hint: 'Furosemide, bendroflumethiazide, indapamide, spironolactone',
  },
  {
    id: 'anticholinergic',
    label: 'Anticholinergic',
    hint: 'Oxybutynin, amitriptyline, solifenacin — these reduce sweating',
  },
  {
    id: 'antipsychotic',
    label: 'Antipsychotic',
    hint: 'Olanzapine, quetiapine, haloperidol, risperidone',
  },
  {
    id: 'ace_arb',
    label: 'Blood pressure — ACE inhibitor or ARB',
    hint: 'Ramipril, lisinopril, losartan, candesartan',
  },
  {
    id: 'beta_blocker',
    label: 'Beta blocker',
    hint: 'Bisoprolol, atenolol, propranolol, carvedilol',
  },
  {
    id: 'ssri',
    label: 'Antidepressant (SSRI)',
    hint: 'Sertraline, citalopram, fluoxetine, paroxetine',
  },
  {
    id: 'heat_sensitive',
    label: 'Insulin or a GTN spray',
    hint: 'These degrade above 25°C and need storing somewhere cool',
  },
]

/** Classify a typed drug name. Unknown names return null rather than throwing —
 *  a typo must not take the assessment down. */
export function classifyMedicine(name: string): string | null {
  return MED_CLASSES[name.trim().toLowerCase()] ?? null
}

/**
 * Heaviest class a person is on, or 0.
 *
 * Used instead of the sum for the same reason `compound()` exists in risk.ts:
 * being on four medicines does not make someone four times as heat-sensitive.
 * The heaviest sets the floor and the rest add half each, capped by soften().
 */
export function medicationBurden(classes: string[]): number {
  const weights = classes
    .map((c) => MED_CLASS_WEIGHTS[c] ?? 0)
    .filter((w) => w > 0)
    .sort((a, b) => b - a)
  if (weights.length === 0) return 0
  const [heaviest, ...rest] = weights
  return heaviest + rest.reduce((sum, w) => sum + w, 0) * 0.5
}

const TIER_RANK: Record<InteractionRule['min_tier'], number> = {
  Low: 0,
  Elevated: 1,
  High: 2,
  Severe: 3,
}

export function tierRank(tier: InteractionRule['min_tier']): number {
  return TIER_RANK[tier]
}

/**
 * Which interaction rules apply.
 *
 * Every declared requirement must hold — that is what makes these combinations
 * rather than a list. `supersedes` is returned alongside so the caller can drop
 * the single-factor advice a rule replaces; emitting both buries the specific
 * instruction under the generic one.
 */
export function matchingInteractions(input: {
  conditions: string[]
  medClasses: string[]
  /** Person-level booleans that are true. */
  flags: string[]
  peakAir: number
  indoorDayEstimate: number
  tier: InteractionRule['min_tier']
  /** What the person told us on a check-in. Absent means they were not asked or
   *  did not answer — which is not the same as answering no. */
  selfReport?: Record<string, boolean | null>
}): InteractionRule[] {
  const conditions = new Set(input.conditions)
  const meds = new Set(input.medClasses)
  const flags = new Set(input.flags)

  return INTERACTIONS.filter((rule) => {
    if (tierRank(input.tier) < tierRank(rule.min_tier)) return false
    if (rule.min_peak_air !== null && input.peakAir < rule.min_peak_air) return false
    if (rule.max_indoor_day !== null && input.indoorDayEstimate > rule.max_indoor_day)
      return false
    if (!rule.requires_conditions.every((c) => conditions.has(c))) return false
    if (!rule.requires_med_classes.every((m) => meds.has(m))) return false
    if (!rule.requires_flags.every((f) => flags.has(f))) return false
    if (rule.requires_self_report) {
      const { field, expected } = rule.requires_self_report
      if (input.selfReport?.[field] !== expected) return false
    }
    return true
  })
}
