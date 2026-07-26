import { assessViaCore, type CoreAssessment } from '@/lib/assess-client'
import { getProvider, ModelRefusalError, type ChatTurn } from '@/lib/llm'
import { isValidProfile, factorLabel, type Profile } from '@/lib/profile'
import { regionByCode } from '@/lib/regions'

/**
 * POST /api/assistant
 *
 * Streams a plain-text reply. Body:
 *   { profile: Profile, messages: ChatTurn[], mode?: 'text' | 'voice',
 *     demo?: 'heat' }
 *
 * `demo` follows the scenario switch on screen. The assistant and the advice
 * panel sit beside each other, so they have to be describing the same day.
 *
 * ────────────────────────────────────────────────────────────────────────────
 *  VOICE LAYER (phase 2) PLUGS IN HERE — no redesign needed.
 *
 *  The browser does speech-to-text on device (Web Speech API), POSTs the
 *  transcript to this same endpoint, and speaks the streamed chunks with
 *  speechSynthesis as they arrive. Pass mode: 'voice' and the system prompt
 *  switches to spoken-length answers with no markdown.
 *
 *  That is why this returns a raw text stream rather than JSON — a text stream
 *  is what a TTS layer wants to consume incrementally.
 * ────────────────────────────────────────────────────────────────────────────
 */

export const runtime = 'nodejs'

function buildSystemPrompt(
  profile: Profile,
  core: CoreAssessment,
  mode: 'text' | 'voice',
): string {
  const region = regionByCode(profile.regionCode)

  const factors = profile.factors.length
    ? profile.factors.map(factorLabel).join('; ')
    : 'none recorded'

  const reasons = core.reasons.length
    ? core.reasons.map((r) => `- ${r.title}: ${r.explanation}`).join('\n')
    : '- none'

  const actions = core.plan.items.length
    ? core.plan.items.map((i) => `- ${i.text}`).join('\n')
    : '- none'

  const watchFor = core.plan.watch_points.length
    ? core.plan.watch_points.map((w) => `- ${w}`).join('\n')
    : ''

  // Only stated when there is a spell to be on day N of. The unconditional
  // version told the model "Day 0 of a heat spell" every January, which is both
  // false and the sort of confident detail it will happily repeat.
  const spell =
    core.exposure.spell_day > 0
      ? `Day ${core.exposure.spell_day} of a heat spell\nRegional heat-health alert: ${core.exposure.alert_level}\n`
      : ''

  // Everything factual is precomputed by the core and handed over, so the model
  // is summarising and answering follow-ups rather than doing arithmetic on
  // temperatures — which is where a model would otherwise get things wrong.
  const context = `
CONDITIONS — ${region?.name ?? profile.regionCode}
Outdoor peak: ${core.exposure.peak_air}°C (feels like ${core.exposure.peak_apparent}°C)
Overnight low: ${core.exposure.overnight_min}°C
Their bedroom tonight: ${core.exposure.indoor_night_est_modelled}°C — MODELLED, not measured
Their home in the daytime: ${core.exposure.indoor_day_est_modelled}°C — MODELLED, not measured
${spell}Source: ${core.exposure.source}

THIS PERSON
Name: ${profile.name}
Risk factors: ${factors}
${profile.notes ? `Their own notes: ${profile.notes}` : ''}

ASSESSMENT (already calculated — do not recalculate)
Tier: ${core.tier} (risk ${core.risk_score}, exposure ${core.exposure_score}, vulnerability ${core.vulnerability_score})

WHY THEY ARE AT RISK
${reasons}

THEIR PREVENTION PLAN
${actions}
${watchFor ? `\nWHAT TO WATCH FOR\n${watchFor}` : ''}
${core.plan.escalate_to.length ? `\nESCALATE TO: ${core.plan.escalate_to.join(', ')}` : ''}
`.trim()

  const lengthRule =
    mode === 'voice'
      ? `This answer will be SPOKEN ALOUD. Keep it to two or three short sentences. No markdown, no lists, no headings, no emoji — write it exactly as a person would say it out loud. Numbers as words where it reads more naturally ("about twenty-nine degrees").`
      : `Keep replies short — usually two to four sentences. Use a short bulleted list only when giving several distinct actions. No headings.`

  return `You are the Climatise assistant. You help people in the UK stay safe when it is too hot or too cold for them personally.

${lengthRule}

HOW TO ANSWER
- Answer the question that was actually asked. Do not recite the whole assessment unprompted.
- The figures and the assessment below are already calculated and correct. Use them as given; never invent or recompute a temperature, and never contradict the tier.
- Your advice must come from THEIR PREVENTION PLAN below. That text has been through a clinical safety review; anything you compose has not.
- Lead with what to do, then briefly why, and only when the why is useful.
- Talk about this person's specific situation. They know their own circumstances — do not explain their conditions back to them.
- Say "modelled" when you mention their indoor temperature. It is an estimate from the forecast and their home, not a reading.
- Plain language. No jargon, no hedging, no disclaimers unless there is a genuine safety reason.
- If they ask something you have no information about (their medication specifics, a diagnosis, anything medical beyond general guidance), say so plainly in one sentence and point them at their GP, pharmacist, or 111.
- Never tell someone to stop or change a prescribed medicine.

CONTEXT
${context}`
}

export async function POST(request: Request) {
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return Response.json({ error: 'Invalid JSON body.' }, { status: 400 })
  }

  const { profile, messages, mode, demo } = (body ?? {}) as {
    profile?: unknown
    messages?: unknown
    mode?: unknown
    demo?: 'heat'
  }

  if (!isValidProfile(profile)) {
    return Response.json({ error: 'A valid profile is required.' }, { status: 400 })
  }

  if (
    !Array.isArray(messages) ||
    messages.length === 0 ||
    !messages.every(
      (m): m is ChatTurn =>
        !!m &&
        typeof m === 'object' &&
        (m.role === 'user' || m.role === 'assistant') &&
        typeof m.content === 'string' &&
        m.content.trim().length > 0,
    )
  ) {
    return Response.json({ error: 'messages must be a non-empty chat history.' }, { status: 400 })
  }

  if (messages.at(-1)?.role !== 'user') {
    return Response.json({ error: 'The last message must be from the user.' }, { status: 400 })
  }

  // Keep the history bounded — the assessment is regenerated every turn, so
  // older turns add cost without adding accuracy.
  const history = messages.slice(-12)

  // A typo must not quietly return live data while the panel beside it shows
  // the fixture. The core 422s an unknown fixture for the same reason.
  if (demo !== undefined && demo !== 'heat') {
    return Response.json(
      { error: `Unknown demo scenario ${JSON.stringify(demo)}. Only 'heat' is supported.` },
      { status: 400 },
    )
  }

  // The core, on the same day the rest of the screen is showing. This used to
  // score with the old TypeScript engine against live weather, so the assistant
  // sat beside the advice panel describing a different day — "a touch warmer
  // than suits you" next to "Dangerously hot for you right now".
  //
  // RegionPanel on `/` is still on the TS engine, so the two now agree on the
  // day but not yet on the vocabulary. Moving it to /api/assess closes that.
  let core: CoreAssessment
  try {
    core = await assessViaCore(profile, demo)
  } catch (error) {
    console.error('[api/assistant] core assessment failed', error)
    return Response.json(
      {
        error:
          'I cannot reach the risk service right now, so I would only be guessing.',
      },
      { status: 503 },
    )
  }

  const system = buildSystemPrompt(profile, core, mode === 'voice' ? 'voice' : 'text')
  const provider = getProvider()

  // Before a single byte goes out. Once the stream opens the status code is
  // spent, and a missing API key would be reported as "try that again" — advice
  // that will never once work.
  const configuration = provider.configured()
  if (!configuration.ok) {
    console.error('[api/assistant] not configured:', configuration.reason)
    // "Unavailable" reads as broken, and a reader who thinks one part is broken
    // reasonably doubts the rest. Naming the cause as configuration says the
    // opposite: nothing has failed, a feature simply is not switched on here —
    // and the risk assessment never depended on it anyway.
    return Response.json(
      {
        error:
          'The assistant is switched off in this demo — it needs an API key that ' +
          'is not configured here. Everything else works: your risk, your plan ' +
          'and your alerts are all computed without it.',
      },
      { status: 503 },
    )
  }

  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for await (const chunk of provider.stream({ system, messages: history })) {
          controller.enqueue(encoder.encode(chunk))
        }
      } catch (error) {
        if (error instanceof ModelRefusalError) {
          controller.enqueue(
            encoder.encode(
              "\n\nI can't help with that one. For anything medical, your GP or NHS 111 is the right place.",
            ),
          )
        } else {
          console.error('[api/assistant] stream failed', error)
          // The response has already started, so an HTTP status is spent —
          // the message has to carry the distinction instead.
          //
          // "Try again" is only honest for a transient fault. An exhausted
          // credit balance or a rejected key will fail identically forever, and
          // telling someone to retry it is the same mistake the pre-flight
          // check above was added to stop.
          controller.enqueue(encoder.encode(`\n\n${describeStreamFailure(error)}`))
        }
      } finally {
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      // Stops proxies buffering the stream, which would defeat the point.
      'X-Accel-Buffering': 'no',
    },
  })
}

/**
 * What to tell the reader when the stream dies mid-flight.
 *
 * Only two outcomes matter to them: is this worth retrying, or is the assistant
 * simply not going to answer today? Everything else is operator detail and
 * belongs in the log, not on a screen someone opened because they were worried.
 */
function describeStreamFailure(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  const unaffected =
    'Your risk and your plan are unaffected — they are computed without it.'

  if (/credit balance|billing|quota|insufficient_quota/i.test(message)) {
    return `The assistant has run out of credit on this account, so it cannot answer right now. ${unaffected}`
  }
  if (/authentication|invalid[ _-]?api[ _-]?key|401|403/i.test(message)) {
    return `The assistant is not set up correctly on this deployment. ${unaffected}`
  }
  if (/rate[ _-]?limit|429|overloaded|529/i.test(message)) {
    return 'The assistant is busy at the moment. Worth trying again in a minute.'
  }
  return 'Something went wrong reaching the assistant. Worth trying again.'
}
