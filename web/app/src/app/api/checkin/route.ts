import { NextResponse } from 'next/server'

import { getAdvice } from '@/lib/advice'
import { DEMO_PROFILES, isValidProfile, type Profile } from '@/lib/profile'
import {
  build as buildQuestionnaire,
  selfReportForRules,
  toSelfReport,
  type Answer,
} from '@/lib/questionnaire'
import { assessRisk, bandLabel } from '@/lib/risk'
import { fetchAllRegions } from '@/lib/weather'

/**
 * The personalised check-in.
 *
 * GET  /api/checkin?id=demo-doris        → the questions this person would be asked
 * GET  /api/checkin?id=demo-doris&at=31  → the same, at a what-if feels-like °C
 * POST /api/checkin  { profile, answers, at? } → what their answers change
 *
 * The what-if matters for more than demos: on a mild day everyone is Low tier
 * and no questions are asked at all, which is correct and makes the behaviour
 * impossible to inspect.
 *
 * The point of the POST is the second assessment. Answers do not just get
 * recorded: a hot-bedroom report unlocks interaction rules that cannot otherwise
 * fire, and red flags escalate. Both assessments are returned so the difference
 * is visible rather than asserted.
 */

async function weatherFor(profile: Profile, at?: number) {
  const snapshot = await fetchAllRegions()
  const weather = snapshot.regions.find((r) => r.regionCode === profile.regionCode)
  if (!weather || at === undefined) return weather
  // Substitute the feels-like figure only. Humidity, wind and today's range stay
  // real, so the answer is "what would this person be told at 31°C", not a
  // wholly invented forecast.
  return {
    ...weather,
    apparentTemperature: at,
    todayApparentMax: Math.max(weather.todayApparentMax, at),
    todayMax: Math.max(weather.todayMax, at),
  }
}

function parseAt(raw: string | null): number | undefined {
  if (raw === null) return undefined
  const value = Number(raw)
  return Number.isFinite(value) && value >= -30 && value <= 55 ? value : undefined
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams
  const id = params.get('id') ?? DEMO_PROFILES[0].id
  const at = parseAt(params.get('at'))
  const profile = DEMO_PROFILES.find((p) => p.id === id)
  if (!profile) {
    return NextResponse.json({ error: `No profile ${id}` }, { status: 404 })
  }

  const weather = await weatherFor(profile, at)
  if (!weather) {
    return NextResponse.json(
      { error: `No weather for region ${profile.regionCode}` },
      { status: 503 },
    )
  }

  const assessment = assessRisk(profile, weather)
  const questionnaire = buildQuestionnaire(profile, assessment)

  return NextResponse.json({
    profile: { id: profile.id, name: profile.name },
    band: bandLabel(assessment.band),
    register: questionnaire.register,
    questions: questionnaire.questions.map((q) => ({
      code: q.code,
      text: q.text,
      screensFor: q.redFlag,
      /** Which answer indicates the flag. Declared, because inferring it would
       *  invert a screen the first time a negatively-phrased question is added. */
      flagsOn: q.redFlag ? (q.redFlagWhen ? 'yes' : 'no') : null,
    })),
  })
}

export async function POST(request: Request) {
  let body: { profile?: unknown; answers?: Record<string, Answer>; at?: number }
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: 'Body must be JSON.' }, { status: 400 })
  }

  if (!isValidProfile(body.profile)) {
    return NextResponse.json({ error: 'Invalid profile.' }, { status: 400 })
  }
  const profile = body.profile
  const answers = body.answers ?? {}

  const weather = await weatherFor(profile, body.at)
  if (!weather) {
    return NextResponse.json(
      { error: `No weather for region ${profile.regionCode}` },
      { status: 503 },
    )
  }

  const before = assessRisk(profile, weather)
  const questionnaire = buildQuestionnaire(profile, before)
  const report = toSelfReport(questionnaire, answers)
  const after = assessRisk(profile, weather, selfReportForRules(report))

  return NextResponse.json({
    profile: { id: profile.id, name: profile.name },
    selfReport: report,
    before: {
      band: bandLabel(before.band),
      severity: before.severity,
      interactions: before.interactions.map((r) => r.code),
    },
    after: {
      band: bandLabel(after.band),
      severity: after.severity,
      interactions: after.interactions.map((r) => r.code),
    },
    /** Rules the answers unlocked. This is what a check-in buys. */
    unlockedByAnswers: after.interactions
      .map((r) => r.code)
      .filter((code) => !before.interactions.some((r) => r.code === code)),
    advice: getAdvice(after),
  })
}
