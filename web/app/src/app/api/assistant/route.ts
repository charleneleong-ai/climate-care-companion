import { getAdvice } from '@/lib/advice'
import { getProvider, ModelRefusalError, type ChatTurn } from '@/lib/llm'
import { isValidProfile, factorLabel, type Profile } from '@/lib/profile'
import { regionByCode } from '@/lib/regions'
import { assessRisk, bandLabel } from '@/lib/risk'
import { describeWeatherCode, fetchAllRegions, type RegionWeather } from '@/lib/weather'

/**
 * POST /api/assistant
 *
 * Streams a plain-text reply. Body:
 *   { profile: Profile, messages: ChatTurn[], mode?: 'text' | 'voice' }
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
  weather: RegionWeather,
  mode: 'text' | 'voice',
): string {
  const assessment = assessRisk(profile, weather)
  const advice = getAdvice(assessment)
  const region = regionByCode(profile.regionCode)

  const factors = profile.factors.length
    ? profile.factors.map(factorLabel).join('; ')
    : 'none recorded'

  const drivers = assessment.drivers.length
    ? assessment.drivers.map((d) => `- ${d.label}`).join('\n')
    : '- none'

  const actions = advice.actions
    .map((a) => `- [${a.priority}, ${a.when}] ${a.text}`)
    .join('\n')

  // Everything factual the model needs is precomputed and handed over, so it
  // is summarising and answering follow-ups rather than doing arithmetic on
  // temperatures — which is where a model would otherwise get things wrong.
  const context = `
CURRENT CONDITIONS — ${region?.name ?? profile.regionCode}
Temperature: ${weather.temperature.toFixed(1)}°C (feels like ${weather.apparentTemperature.toFixed(1)}°C)
Conditions: ${describeWeatherCode(weather.weatherCode)}
Humidity: ${weather.humidity}%  Wind: ${Math.round(weather.windSpeed)} km/h
Today's range: ${weather.todayMin.toFixed(0)}°C to ${weather.todayMax.toFixed(0)}°C (feels like ${weather.todayApparentMin.toFixed(0)}°C to ${weather.todayApparentMax.toFixed(0)}°C)

THIS PERSON
Name: ${profile.name}
Risk factors: ${factors}
${profile.notes ? `Their own notes: ${profile.notes}` : ''}

ASSESSMENT (already calculated — do not recalculate)
Band: ${bandLabel(assessment.band)} (severity ${assessment.severity}/100)
Their personal comfortable range: ${assessment.thresholds.coldModerate.toFixed(0)}°C to ${assessment.thresholds.heatModerate.toFixed(0)}°C
${assessment.worseningToday ? 'Conditions get worse later today.' : 'Conditions do not get worse later today.'}

WHY THEY ARE AT RISK
${drivers}

RECOMMENDED ACTIONS
${actions}
${advice.urgentWarning ? `\nEMERGENCY GUIDANCE: ${advice.urgentWarning}` : ''}
`.trim()

  const lengthRule =
    mode === 'voice'
      ? `This answer will be SPOKEN ALOUD. Keep it to two or three short sentences. No markdown, no lists, no headings, no emoji — write it exactly as a person would say it out loud. Numbers as words where it reads more naturally ("about twenty-nine degrees").`
      : `Keep replies short — usually two to four sentences. Use a short bulleted list only when giving several distinct actions. No headings.`

  return `You are the Climatise assistant. You help people in the UK stay safe when it is too hot or too cold for them personally.

${lengthRule}

HOW TO ANSWER
- Answer the question that was actually asked. Do not recite the whole assessment unprompted.
- All the weather figures and the risk assessment below are already calculated and correct. Use them as given; never invent or recompute a temperature.
- Lead with what to do, then briefly why, and only when the why is useful.
- Talk about this person's specific situation. They know their own circumstances — do not explain their conditions back to them.
- Plain language. No jargon, no hedging, no disclaimers unless there is a genuine safety reason.
- If they ask something you have no information about (their medication specifics, a diagnosis, anything medical beyond general guidance), say so plainly in one sentence and point them at their GP, pharmacist, or 111.
- If the emergency guidance below applies to what they are describing, say it immediately and first.
- Never tell someone to stop taking prescribed medication.

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

  const { profile, messages, mode } = (body ?? {}) as {
    profile?: unknown
    messages?: unknown
    mode?: unknown
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

  let weather: RegionWeather | undefined
  try {
    const snapshot = await fetchAllRegions()
    weather = snapshot.regions.find((r) => r.regionCode === profile.regionCode)
  } catch (error) {
    console.error('[api/assistant] weather fetch failed', error)
    return Response.json(
      { error: 'I cannot reach the weather service right now, so I would only be guessing.' },
      { status: 503 },
    )
  }

  if (!weather) {
    return Response.json(
      { error: `No weather data for region ${profile.regionCode}.` },
      { status: 422 },
    )
  }

  const system = buildSystemPrompt(profile, weather, mode === 'voice' ? 'voice' : 'text')
  const provider = getProvider()

  // Before a single byte goes out. Once the stream opens the status code is
  // spent, and a missing API key would be reported as "try that again" — advice
  // that will never once work.
  const configuration = provider.configured()
  if (!configuration.ok) {
    console.error('[api/assistant] not configured:', configuration.reason)
    return Response.json(
      {
        error:
          'The assistant is not available. Everything else in the app — your risk, ' +
          'your plan, your alerts — works without it.',
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
          // The response has already started, so an HTTP error code is no
          // longer available — surface it in the stream instead.
          controller.enqueue(
            encoder.encode('\n\nSomething went wrong on my end. Please try that again.'),
          )
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
