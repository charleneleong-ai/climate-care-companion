# Climatise

Personalised heat and cold advice for every region of the UK. The premise: the
temperature that is merely uncomfortable for one person is dangerous for
another, so the advice should differ even when the weather does not.

Built as an installable web app (PWA) so anyone can use it from a phone browser
with no app store and no account.

---

## Run it

```bash
npm install
cp .env.example .env.local     # add ANTHROPIC_API_KEY for the assistant
npm run dev                    # http://localhost:3000
```

Weather and postcode lookup need **no API keys**. Only the assistant needs one,
and the rest of the app works without it.

To check everything against live weather:

```bash
npm run build && npm run start &
node scripts/verify.mjs 3000
```

That prints current conditions for all 12 regions, runs the five demo personas
through the risk engine, and stress-tests them at fixed temperatures. It exits
non-zero if personalisation stops producing different results per person.

---

## What is built

| Piece | Where | State |
|---|---|---|
| UK map backbone — all 12 regions, tappable, choropleth by risk | `src/components/UKMap.tsx` | Done |
| Live weather for every region | `src/lib/weather.ts` | Done |
| Personal risk banding | `src/lib/risk.ts` | Done |
| Advice content | `src/lib/advice.ts` | **Baseline only — someone else owns this** |
| Onboarding, no account needed | `src/app/onboarding/page.tsx` | Done |
| Design system / tokens | `src/app/globals.css`, `src/components/ui.tsx` | Done |
| 5 demo personas | `src/lib/profile.ts` | Done |
| Assistant (streaming text chat) | `src/components/Assistant.tsx` | Done, voice not yet wired |
| Installable to home screen | `public/manifest.webmanifest`, `public/sw.js` | Done |

---

## Design

The direction is **civic clarity** — closer to a public-service form than a
consumer app, because the people who most need this may be frail, unwell, or
worried. Every token in `globals.css` is constrained by that audience:

- Body text never below 17px; headings large and heavy
- Tap targets never below 48px (`--tap`)
- Text contrast at least 7:1 (WCAG AAA)
- Colour is never the only signal — always paired with text or shape
- Motion is subtle and fully removed under `prefers-reduced-motion`
- Full light and dark themes

Onboarding is one question per screen with a visible "step N of 4" and a sticky
action bar, so the primary button is always under a thumb. Two details worth
keeping:

- **The location step reveals the live temperature** as soon as a postcode
  resolves. The app proves it works *before* asking anything personal, which is
  where people decide whether to trust it.
- **The review screen shows the outcome, not just the inputs** — the user's own
  risk band and personal comfort range, computed with the real engine. It makes
  the point of the form obvious at the moment they finish it.

Only the icons are still placeholders.

---

## If you are writing the advice content

**You only need to touch `src/lib/advice.ts`.** Nothing else.

`getAdvice(assessment)` receives a fully-computed `RiskAssessment` and returns
an `Advice`. You never call a weather API, never parse a postcode, never touch
the map. What you get:

| Field | What it gives you |
|---|---|
| `band` | One of 7: `cold-severe` … `comfortable` … `heat-severe` |
| `severity` | 0–100, for urgency *within* a band |
| `drivers` | Ranked list of *why* this person is at risk — the hooks for specific advice |
| `thresholds` | Their personalised cut-offs, already adjusted |
| `headroomToNextBand` | °C until they cross into a worse band |
| `worseningToday` | Whether today's forecast gets worse than right now |
| `weather` | The raw conditions, if you need them |

Iterate without touching the UI:

```bash
# All five personas against live weather
curl -s localhost:3000/api/assess | jq

# One persona
curl -s 'localhost:3000/api/assess?id=demo-doris' | jq '.results[0].advice'

# What-if: what will Doris be told when it feels like -2°C?
curl -s 'localhost:3000/api/assess?id=demo-doris&at=-2' | jq '.results[0].advice'

# Any profile you invent
curl -s localhost:3000/api/assess -X POST -H 'content-type: application/json' \
  -d '{"profile":{"id":"t1","name":"Test","regionCode":"TLI","factors":["over75","coldHome"],"createdAt":"2026-07-25T00:00:00Z"}}' | jq
```

Whatever you return also becomes the assistant's context automatically — so
improving the advice improves the chat answers, with no prompt changes.

---

## How the risk model works

Baseline thresholds for a healthy adult, in **apparent** ("feels like")
temperature, anchored on UKHSA Adverse Weather and Health Plan guidance:

```
  0°C        5°C        12°C ───── 22°C       27°C       32°C
  │ severe   │ high     │ moderate │ comfortable │ moderate │ high │ severe
  ←──────────── cold ──────────────┼──────────── heat ────────────→
```

Each vulnerability factor pulls those thresholds inward. Two things stop that
going wrong:

- **Factors compound with diminishing returns, not by summing.** Being over 75
  *and* having a heart condition *and* a cold home does not make someone three
  times as cold-sensitive. The largest factor counts fully; the rest count half.
- **Comfort edges and danger edges move by different amounts**, through a
  saturating curve. Vulnerability barely changes when you stop feeling
  comfortable; it changes a lot how fast that becomes dangerous.

`personalThresholds()` asserts the six thresholds stay strictly increasing, so
the bands can never cross. Both of those guards exist because the first version
had real bugs: summing collapsed the comfortable band until it inverted (making
"comfortable" unreachable for frail profiles), and a hard cap then saturated for
every persona, so all five were shown an identical "comfortable range" while the
UI claimed it was personalised. `scripts/verify.mjs` checks both.

`assessRisk()` is a pure function — no I/O, no clock, no randomness.

---

## Adding voice (phase 2)

The seam is already in place; no redesign needed.

`POST /api/assistant` takes text and **streams plain text back**, which is
exactly what a text-to-speech layer wants to consume incrementally. To add
voice:

1. Web Speech API (`SpeechRecognition`) transcribes on device → fills the input.
2. POST to the same endpoint with `mode: 'voice'` — the system prompt switches
   to two-or-three-sentence spoken answers with no markdown.
3. Feed the streamed chunks to `speechSynthesis` as they arrive.

Both speech steps run on the phone, so voice costs nothing beyond the existing
model call.

---

## Architecture

```
Open-Meteo ──→ lib/weather.ts ──┐
                                ├──→ lib/risk.ts ──→ lib/advice.ts ──→ UI
localStorage ──→ lib/profile.ts ┘      (the seam)     (teammate's)
                                                │
postcodes.io ──→ /api/postcode                  └──→ /api/assistant ──→ Claude
```

**Data sources** (both free, neither needs a key):
- [Open-Meteo](https://open-meteo.com) — current conditions and forecast
- [postcodes.io](https://postcodes.io) — postcode → region
- Region boundaries: ONS `ITL1_JAN_2025_UK_BUC`, simplified to 4dp (~640 KB,
  gzips to ~180 KB)

**Notable choices**
- The map renders boundary polygons with **no tile layer** — instant load, no
  external tile requests or attribution, works offline, and reads as a data
  visualisation rather than a street map.
- **Leaflet is driven directly, not via react-leaflet.** react-leaflet v4 does
  not survive React StrictMode's deliberate double-mount in dev: it leaves
  Leaflet's `_leaflet_id` on the container and the second mount throws "Map
  container is already initialized", crashing `npm run dev`. Owning the
  lifecycle in `UKMap.tsx` means one explicit `map.remove()` in cleanup fixes
  it, and react-leaflet is no longer a dependency.
- **Baseline banding on the map, personal banding for your own region.** The map
  shows the *place*, so it must look the same to everyone; selecting a region you
  are not in deliberately does not pretend your advice applies there.
- **Apparent temperature everywhere**, not dry-bulb. Wind chill and humidity are
  what make a nominally mild day dangerous.
- **Only the outward postcode is ever stored** (`B15`, not `B15 2TT`) — enough
  for a region, not a household.
- Profiles live in `localStorage`; the server registry is in-memory. Swap
  `getProfileStore()` for a Postgres implementation and nothing else changes.

---

## Deploying

```bash
npx vercel            # set ANTHROPIC_API_KEY in the dashboard
```

Anyone can then open the URL on a phone and add it to their home screen.

---

## Known gaps

- **Advice content is a baseline**, not finished copy.
- **Voice is not wired up** — the endpoint is ready for it.
- **The server profile registry is in-memory**, so it resets on cold start. The
  client copy in `localStorage` means users are not affected; only the shared
  roster is.
- No tests beyond `scripts/verify.mjs`.
- Icons are placeholders.

---

Weather from Open-Meteo. Guidance based on the UKHSA Adverse Weather and Health
Plan and NHS heat and cold guidance. General guidance only — not medical advice.
