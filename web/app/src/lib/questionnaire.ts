/**
 * The personalised check-in questionnaire.
 *
 * Mirrors checkin/questions.py. Selection from a validated bank, never
 * generation: an unsupervised set of health questions put to an 88-year-old has
 * to be auditable line by line, and a composed question is not.
 *
 * Four axes, all visible in `build`:
 *   which     — the reason codes active for this person
 *   how many  — a cap by tier, lower again in the simplified register
 *   phrasing  — dementia selects a single-clause register
 *   meaning   — answer_field and red-flag polarity, both declared not inferred
 */

import generated from '@/generated/questions.generated.json'
import { activeCodes, TIER_FOR_BAND } from './codes'
import type { Profile } from './profile'
import type { RiskAssessment } from './risk'

export type Register = 'standard' | 'simple'
export type Answer = boolean | null

export interface QuestionRow {
  code: string
  reason_code: string | null
  tier_min: 'Low' | 'Elevated' | 'High' | 'Severe'
  text: string
  text_simple: string
  answer_field: string | null
  red_flag: string | null
  red_flag_when: boolean
  ordering: number
}

export interface Question {
  code: string
  text: string
  answerField: string | null
  redFlag: string | null
  redFlagWhen: boolean
}

export interface Questionnaire {
  register: Register
  questions: Question[]
}

/** What a completed check-in produces. Mirrors the core's SelfReport. */
export interface SelfReport {
  answered: boolean
  bedroomFeelsHot: Answer
  drinkingFluids: Answer
  redFlags: string[]
}

const ROWS = generated.questions as QuestionRow[]
const MAX_BY_TIER = generated.max_by_tier as Record<string, number>
const SIMPLE_MAX = generated.simple_register_max as number

const TIER_RANK = { Low: 0, Elevated: 1, High: 2, Severe: 3 } as const

function phrased(row: QuestionRow, register: Register): string {
  return register === 'simple' ? row.text_simple : row.text
}

export function maxQuestions(
  tier: keyof typeof TIER_RANK,
  register: Register,
): number {
  const cap = MAX_BY_TIER[tier] ?? 0
  return register === 'simple' ? Math.min(cap, SIMPLE_MAX) : cap
}

/**
 * Build this person's questionnaire.
 *
 * Red-flag screens are exempt from the cap. A truncated questionnaire must never
 * be how an SC-3 screen goes unasked, and someone who triggers many reason codes
 * is precisely the person most likely to need one.
 */
export function build(profile: Profile, assessment: RiskAssessment): Questionnaire {
  const register: Register = profile.factors.includes('dementia') ? 'simple' : 'standard'
  const tier = TIER_FOR_BAND[assessment.band]

  if (tier === 'Low') return { register, questions: [] }

  const active = new Set(
    activeCodes({
      factors: profile.factors,
      medClasses: profile.medClasses ?? [],
      weather: assessment.weather,
      band: assessment.band,
    }),
  )

  const applicable = ROWS.filter(
    (row) =>
      TIER_RANK[tier] >= TIER_RANK[row.tier_min] &&
      (row.reason_code === null || active.has(row.reason_code)),
  ).sort((a, b) => a.ordering - b.ordering)

  const seen = new Set<string>()
  const ordinary: QuestionRow[] = []
  const redFlags: QuestionRow[] = []

  for (const row of applicable) {
    const text = phrased(row, register)
    if (seen.has(text)) continue
    seen.add(text)
    ;(row.red_flag ? redFlags : ordinary).push(row)
  }

  const kept = [...ordinary.slice(0, maxQuestions(tier, register)), ...redFlags].sort(
    (a, b) => a.ordering - b.ordering,
  )

  return {
    register,
    questions: kept.map((row) => ({
      code: row.code,
      text: phrased(row, register),
      answerField: row.answer_field,
      redFlag: row.red_flag,
      redFlagWhen: row.red_flag_when,
    })),
  }
}

/**
 * Fold answers into a SelfReport.
 *
 * An empty answer set means the check-in was not answered — a first-class
 * outcome, not an error. Unanswered individual questions stay null rather than
 * being read as "no": absent is not a denial.
 */
export function toSelfReport(
  questionnaire: Questionnaire,
  answers: Record<string, Answer>,
): SelfReport {
  const fields: Record<string, Answer> = {}
  const redFlags: string[] = []

  for (const question of questionnaire.questions) {
    const answer = answers[question.code]
    if (answer === undefined || answer === null) continue
    if (question.answerField) fields[question.answerField] = answer
    if (question.redFlag && answer === question.redFlagWhen) redFlags.push(question.redFlag)
  }

  return {
    answered: Object.keys(answers).length > 0,
    bedroomFeelsHot: fields.bedroom_feels_hot ?? null,
    drinkingFluids: fields.drinking_fluids ?? null,
    redFlags,
  }
}

/** The shape `matchingInteractions` expects, so a check-in unlocks the
 *  self-report rules that otherwise can never fire. */
export function selfReportForRules(report: SelfReport): Record<string, boolean | null> {
  return {
    bedroom_feels_hot: report.bedroomFeelsHot,
    drinking_fluids: report.drinkingFluids,
  }
}
