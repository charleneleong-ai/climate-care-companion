/**
 * The questions offered before anyone has typed anything.
 *
 * They were seeded from the risk direction alone, so every person in hot
 * weather was offered the same three. That is a small thing everywhere except
 * here: the argument this whole product makes is that the same weather means
 * different things to different people, and a row of identical prompts quietly
 * says the opposite on the first screen someone sees.
 *
 * One prompt was worse than merely generic. "How much should I be drinking?"
 * was offered to everybody, including the people for whom the honest answer is
 * a number their GP has set and not the "plenty" the internet will tell them.
 * Victor — heart failure, a diuretic, reduced kidney function — is the case the
 * demo is built around, and the old list invited exactly the question the
 * system exists to answer differently. Fluid prompts are now phrased so the
 * answer has to be personal, or not offered at all.
 *
 * Ordered most specific first, then trimmed. A prompt earns its place by
 * naming something true about this person; the general ones are a floor, not a
 * default.
 */

import type { Profile } from './profile'
import type { RiskDirection } from './risk'

/** Kept small on purpose — four chips is a menu, eight is a wall of text. */
const LIMIT = 4

export interface SuggestionContext {
  /** Reuses the engine's own union rather than restating it — a second copy is
   *  how 'none' and 'neutral' end up meaning the same thing in two files. */
  direction: RiskDirection
  worseningToday: boolean
}

interface Rule {
  /** Why this prompt exists, for whoever changes the wording later. */
  because: string
  when: (profile: Profile, context: SuggestionContext) => boolean
  text: string
}

const has = (profile: Profile, factor: string) => profile.factors.includes(factor)
const takes = (profile: Profile, cls: string) => (profile.medClasses ?? []).includes(cls)
const classCount = (profile: Profile) => new Set(profile.medClasses ?? []).size

/**
 * Fluid is a tightrope rather than a target for these people: the kidneys
 * cannot clear an excess, or a heart-failure restriction is already in place.
 * "Drink plenty" is the wrong advice and a prompt inviting it is the wrong
 * question, so the personal version replaces the general one below.
 */
const fluidIsRestricted = (profile: Profile) =>
  has(profile, 'renal') || (has(profile, 'cardiovascular') && takes(profile, 'diuretic'))

const RULES: Rule[] = [
  {
    because: 'Fluid balance is personal for them, and the generic prompt is unsafe.',
    when: (p, c) => c.direction === 'heat' && fluidIsRestricted(p),
    text: 'How much should I drink, with my condition?',
  },
  {
    because: 'Overlapping medicines are the thing MED_POLYPHARMACY scores.',
    when: (p) => classCount(p) >= 3,
    text: 'Do my medicines work against each other in this weather?',
  },
  {
    because: 'A single heat-acting medicine still changes the advice.',
    when: (p) => classCount(p) > 0 && classCount(p) < 3,
    text: 'Does my medication change what I should do today?',
  },
  {
    because: 'Nobody would notice them deteriorating.',
    when: (p) => has(p, 'livesAlone'),
    text: 'Who should I contact if I start feeling unwell?',
  },
  {
    because: 'The building is the problem, so cooling advice is the useful kind.',
    when: (p, c) => c.direction === 'heat' && has(p, 'overheatingHome'),
    text: 'My home gets very hot — what actually helps?',
  },
  {
    because: 'Rationed heating needs advice that does not assume they can spend.',
    when: (p, c) => c.direction === 'cold' && has(p, 'coldHome'),
    text: 'Which room should I heat if I cannot heat them all?',
  },
  {
    because: 'They may not be able to move to a cooler room unaided.',
    when: (p) => has(p, 'mobility'),
    text: 'I cannot move around easily — what can I do from here?',
  },
  {
    because: 'Heat and cold both worsen breathing, and they will feel it first.',
    when: (p) => has(p, 'respiratory'),
    text: 'What does this weather do to my breathing?',
  },
  {
    because: 'They may not notice the change themselves, so the reader is often a carer.',
    when: (p) => has(p, 'dementia'),
    text: 'What should someone look for when they visit?',
  },
  {
    because: 'The forecast turns later, which is the whole point of warning early.',
    when: (_p, c) => c.worseningToday,
    text: 'What changes later today?',
  },
]

/** Offered to everyone, and last — a floor rather than a default. */
const GENERAL: Record<RiskDirection, string[]> = {
  // The drink question stays for the people it is safe for — most of them. It
  // is removed below only where the answer is a personal limit, rather than
  // dropped for everyone to protect the few.
  heat: ['What should I do right now?', 'How much should I be drinking?', 'How do I cool my home down?'],
  cold: ['What should I do right now?', 'How do I keep warm safely?'],
  none: ['What should I do today?', 'What should I watch out for later?'],
}

export function suggestionsFor(
  profile: Profile | null,
  context: SuggestionContext | null,
): string[] {
  if (!profile || !context) return ['What should I do today?']

  const personal = RULES.filter((rule) => rule.when(profile, context)).map((r) => r.text)

  // The general fluid question is dropped entirely for anyone on a restriction,
  // rather than sitting alongside the personal one and inviting the comparison.
  const general = GENERAL[context.direction].filter(
    (text) => !(text.includes('drink') && fluidIsRestricted(profile)),
  )

  return [...new Set([...personal, ...general])].slice(0, LIMIT)
}
