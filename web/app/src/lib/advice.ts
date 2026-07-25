/**
 * ════════════════════════════════════════════════════════════════════════════
 *  THIS FILE IS THE ADVICE LAYER — OWNED BY WHOEVER IS WRITING THE GUIDANCE.
 *
 *  Everything else in the app is done and does not need to change. Replace
 *  the body of `getAdvice()` below with the real content. The contract:
 *
 *      getAdvice(assessment: RiskAssessment) => Advice
 *
 *  You get a fully-computed `RiskAssessment` (see risk.ts): the band, a 0-100
 *  severity, a ranked list of *why* this person is at risk (`drivers`), their
 *  personalised thresholds, and whether today gets worse. You never have to
 *  call a weather API or know anything about the map.
 *
 *  The assistant (assistant/route.ts) is handed whatever you return here and
 *  told to work from it, so improving this file improves the voice/chat
 *  answers too — you do not need to touch the prompt.
 *
 *  What is here now is a deliberately plain baseline so the app runs
 *  end-to-end. It is not the finished content.
 * ════════════════════════════════════════════════════════════════════════════
 */

import type { RiskAssessment, RiskBand } from './risk'

export interface AdviceAction {
  /** Stable id, useful for analytics or for marking an action as done. */
  id: string
  /** The instruction itself. Imperative, specific, one action per item. */
  text: string
  /** `now` shows first; `today` and `ongoing` are grouped after it. */
  when: 'now' | 'today' | 'ongoing'
  /** `critical` actions are visually escalated and read out first by voice. */
  priority: 'critical' | 'important' | 'helpful'
  /** Optional — set when this action exists because of a specific risk driver. */
  becauseOf?: string
}

export interface Advice {
  /** One-line summary. Shown as the headline and spoken first by the assistant. */
  headline: string
  /** Short plain-language explanation of what is going on. 1-2 sentences. */
  summary: string
  actions: AdviceAction[]
  /** Shown as a red banner and always spoken. Use for genuine emergencies. */
  urgentWarning?: string
  /** Where the guidance comes from, for the footer. */
  sources?: string[]
}

/** Baseline copy per band. Replace with the real content. */
const BAND_COPY: Record<RiskBand, { headline: string; summary: string }> = {
  'cold-severe': {
    headline: 'Dangerously cold for you right now',
    summary:
      'It is cold enough to be a real risk to your health, not just uncomfortable. Getting warm is the priority.',
  },
  'cold-high': {
    headline: 'Cold enough to affect your health',
    summary:
      'At this temperature your body works harder to stay warm, which puts strain on your heart and lungs.',
  },
  'cold-moderate': {
    headline: 'Chilly — worth taking care',
    summary: 'Not dangerous, but easy to get too cold if you are out for a while or sitting still indoors.',
  },
  comfortable: {
    headline: 'Comfortable conditions',
    summary: 'Nothing to do differently today. Conditions are in a good range for you.',
  },
  'heat-moderate': {
    headline: 'Warm — keep an eye on it',
    summary: 'Pleasant for most people, but worth drinking more than usual and staying out of direct sun.',
  },
  'heat-high': {
    headline: 'Hot enough to affect your health',
    summary:
      'At this temperature dehydration and heat exhaustion build up gradually, often before you notice.',
  },
  'heat-severe': {
    headline: 'Dangerously hot for you right now',
    summary: 'This level of heat is a real risk to your health. Cooling down is the priority.',
  },
}

/** Baseline actions per band. Replace with the real content. */
function baselineActions(band: RiskBand): AdviceAction[] {
  switch (band) {
    case 'cold-severe':
    case 'cold-high':
      return [
        {
          id: 'heat-one-room',
          text: 'Heat one room to at least 18°C and stay in it rather than heating the whole house.',
          when: 'now',
          priority: 'critical',
        },
        {
          id: 'layers',
          text: 'Wear several thin layers rather than one thick one, and keep your head and feet covered.',
          when: 'now',
          priority: 'important',
        },
        {
          id: 'hot-drinks',
          text: 'Have a hot drink and at least one hot meal — food is what your body burns to make heat.',
          when: 'now',
          priority: 'important',
        },
        {
          id: 'move-hourly',
          text: 'Get up and move around every hour. Sitting still for long periods lets your core temperature drop.',
          when: 'today',
          priority: 'important',
        },
      ]
    case 'cold-moderate':
      return [
        {
          id: 'layer-up',
          text: 'Add a layer before you go out — it is colder than it looks.',
          when: 'now',
          priority: 'helpful',
        },
        {
          id: 'keep-18',
          text: 'Keep your main room at 18°C or above.',
          when: 'today',
          priority: 'helpful',
        },
      ]
    case 'comfortable':
      return [
        {
          id: 'no-action',
          text: 'No specific precautions needed today.',
          when: 'today',
          priority: 'helpful',
        },
      ]
    case 'heat-moderate':
      return [
        {
          id: 'drink-water',
          text: 'Drink water regularly rather than waiting until you feel thirsty.',
          when: 'now',
          priority: 'helpful',
        },
        {
          id: 'avoid-peak-sun',
          text: 'Stay out of direct sun between 11am and 3pm where you can.',
          when: 'today',
          priority: 'helpful',
        },
      ]
    case 'heat-high':
    case 'heat-severe':
      return [
        {
          id: 'find-cool-room',
          text: 'Move to the coolest room you have, ideally one that faces away from the sun.',
          when: 'now',
          priority: 'critical',
        },
        {
          id: 'water-hourly',
          text: 'Drink a glass of water every hour, even if you are not thirsty.',
          when: 'now',
          priority: 'critical',
        },
        {
          id: 'close-curtains',
          text: 'Close curtains and blinds on the sunny side of your home, and open windows only once it is cooler outside than in.',
          when: 'now',
          priority: 'important',
        },
        {
          id: 'cool-skin',
          text: 'Cool your skin directly — a damp cloth on the back of your neck and wrists works quickly.',
          when: 'now',
          priority: 'important',
        },
        {
          id: 'no-exertion',
          text: 'Postpone anything strenuous until the evening.',
          when: 'today',
          priority: 'important',
        },
      ]
  }
}

/** Actions triggered by a specific driver rather than the band alone. */
function driverActions(assessment: RiskAssessment): AdviceAction[] {
  const actions: AdviceAction[] = []
  const has = (id: string) => assessment.drivers.some((d) => d.id === id)

  if (has('livesAlone') && assessment.severity >= 50) {
    actions.push({
      id: 'check-in',
      text: 'Arrange for someone to check on you today — a phone call is enough.',
      when: 'now',
      priority: 'critical',
      becauseOf: 'livesAlone',
    })
  }
  if (has('medication') && assessment.direction === 'heat') {
    actions.push({
      id: 'medication-heat',
      text: 'Some medicines make you dehydrate faster or mask the signs of overheating. Do not stop taking them — ask your pharmacist whether yours are affected.',
      when: 'today',
      priority: 'important',
      becauseOf: 'medication',
    })
  }
  if (has('respiratory') && assessment.direction === 'cold') {
    actions.push({
      id: 'respiratory-cold',
      text: 'Cover your mouth and nose with a scarf outdoors so you breathe warmed air, and keep your reliever inhaler with you.',
      when: 'now',
      priority: 'important',
      becauseOf: 'respiratory',
    })
  }
  if (has('warmNight')) {
    actions.push({
      id: 'night-cooling',
      text: 'It will not cool down much overnight. Cool your bedroom during the day and use a damp sheet rather than a duvet.',
      when: 'today',
      priority: 'important',
      becauseOf: 'warmNight',
    })
  }
  if (has('freezingNight')) {
    actions.push({
      id: 'night-warmth',
      text: 'It drops below freezing tonight. Heat your bedroom before you go up, and keep a hot water bottle or extra blanket to hand.',
      when: 'today',
      priority: 'important',
      becauseOf: 'freezingNight',
    })
  }
  if (has('coldHome')) {
    actions.push({
      id: 'cold-home-support',
      text: 'You may be eligible for help with heating costs — the Winter Fuel Payment and the Warm Home Discount are worth checking.',
      when: 'ongoing',
      priority: 'helpful',
      becauseOf: 'coldHome',
    })
  }
  if (has('outdoorWork')) {
    actions.push({
      id: 'outdoor-breaks',
      text:
        assessment.direction === 'heat'
          ? 'Take breaks in shade every 30 minutes and drink at each break, not just at lunch.'
          : 'Take breaks somewhere genuinely warm every hour, and change out of anything damp straight away.',
      when: 'today',
      priority: 'important',
      becauseOf: 'outdoorWork',
    })
  }

  return actions
}

function urgentWarningFor(assessment: RiskAssessment): string | undefined {
  if (assessment.band === 'heat-severe') {
    return 'If you or someone near you has a headache with confusion, stops sweating, or has hot dry skin, that may be heatstroke. Call 999.'
  }
  if (assessment.band === 'cold-severe') {
    return 'If you or someone near you is shivering uncontrollably, slurring words, or unusually drowsy, that may be hypothermia. Call 999.'
  }
  return undefined
}

/**
 * Turn a risk assessment into advice.
 *
 * Pure function — no I/O — so it can run on the server for the assistant's
 * context and on the client for the UI, and always produce the same result.
 */
export function getAdvice(assessment: RiskAssessment): Advice {
  const copy = BAND_COPY[assessment.band]

  const actions = [...baselineActions(assessment.band), ...driverActions(assessment)]

  // Critical first, then by when. Keeps the spoken version useful if the
  // listener stops paying attention after the first sentence.
  const priorityRank = { critical: 0, important: 1, helpful: 2 } as const
  const whenRank = { now: 0, today: 1, ongoing: 2 } as const
  actions.sort(
    (a, b) =>
      priorityRank[a.priority] - priorityRank[b.priority] || whenRank[a.when] - whenRank[b.when],
  )

  let summary = copy.summary
  if (assessment.worseningToday && assessment.band !== 'comfortable') {
    summary += ' It gets worse later today, so act now rather than waiting.'
  } else if (assessment.worseningToday) {
    summary = `${summary} Conditions do get less comfortable later today.`
  }

  return {
    headline: copy.headline,
    summary,
    actions,
    urgentWarning: urgentWarningFor(assessment),
    sources: ['UKHSA Adverse Weather and Health Plan', 'NHS heat and cold guidance'],
  }
}
