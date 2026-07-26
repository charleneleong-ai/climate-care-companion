# Deployment guide

Demonstrator only. Not medical advice, not clinically validated.

## Architecture

Two processes share one machine:

| Process | Default port | Command |
|---|---|---|
| Python risk API | 8000 | `uv run uvicorn api.main:app --port 8000` |
| Next.js frontend | 3000 | `cd web/app && npm start` |

The frontend calls the API server-side (`CORE_API_URL`, default `http://localhost:8000`).
Weather comes from [Open-Meteo](https://open-meteo.com) — no API key needed.

---

## Local development

```bash
# 1. Install Python deps
uv sync --all-packages

# 2. Run the Python API (hot-reload)
uv run uvicorn api.main:app --port 8000 --reload

# 3. Install JS deps and start Next.js dev server
cd web/app && npm install && npm run dev -- --port 3000
```

Open http://localhost:3000.

---

## Production build (demo machine)

```bash
# Python API — start once, runs until killed
uv run uvicorn api.main:app --port 8000 --log-level warning > /tmp/api.log 2>&1 &

# Build the Next.js app
cd web/app
npm install          # first time only, or after pulling new code
npm run build        # creates .next/ production bundle

# Start the production server
npm start -- --port 3000 > /tmp/next.log 2>&1 &
```

Verify both are running:
```bash
curl http://localhost:8000/health
curl -o /dev/null -w "%{http_code}" http://localhost:3000
```

---

## Public URL via Cloudflare Quick Tunnel

No account required. Each run generates a new random `*.trycloudflare.com` URL.

```bash
cloudflared tunnel --url http://localhost:3000 > /tmp/tunnel.log 2>&1 &
sleep 8
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/tunnel.log | head -1
```

Share that URL. The tunnel stays alive as long as the process runs.

> Note: if `node_modules` is a symlink (check with `ls -la web/app/node_modules`),
> remove it and run `npm install` to create a real directory before building.

---

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `CORE_API_URL` | `web/app/.env.local` | Override Python API URL (default `http://localhost:8000`) |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | `web/app/.env.local` | Web push notifications (optional) |
| `ANTHROPIC_API_KEY` | `web/app/.env.local` | Assistant (optional — without it the panel says so and everything else still works) |
| `TWILIO_*` | `.env` | WhatsApp/SMS check-in channel (optional) |

---

## Demo routes

All views default to the **19 July 2025 heatwave scenario** — repeatable regardless of today's weather.

| URL | View | Default audience | Notes |
|---|---|---|---|
| `/` | Map + Your advice | — | UK map goes amber/red in England; "Your advice" shows heatwave risk |
| `/personal` | Personal view | Person themselves | "Your situation tonight" |
| `/caregiver` | Caregiver view | Caregiver | Escalation routes prominent; Watch-fors prominent |
| `/monitoring` | Population dashboard | — | Cohort risk across the three days of the episode, plus the UK choropleth |
| `/onboarding` | Set up a profile | — | Collects name, postcode, conditions, meds |
| `/companion` | Legacy companion | Caregiver | Same as `/caregiver`; kept for backward compat |

Toggle between heatwave and live weather using the banner button on each view, or:
- `?demo=live` in the URL pre-selects live weather
- `?demo=heat` on GET `/api/assess` forces the fixture server-side
- `POST /api/assistant` takes the same `demo: "heat"`, so the assistant answers
  about the day on screen rather than live weather

---

## The heatwave scenario (19 July 2025)

**Fixture date:** Saturday 19 July 2025 · Bedford, East of England
**Conditions:** 29°C peak apparent · overnight 17°C (no recovery) · Day 3 of sustained heat
**National alert:** None — no heat-health alert was issued in any English region
**Excess deaths:** ~146 (UKHSA Episode 4: 17–19 July 2025)

### Demo cohort tiers on that day

| Profile | Tier | Vuln | Interactions | Demo argument |
|---|---|---|---|---|
| Victor | **HIGH** | 14 | 14 | "Drink plenty" is the wrong advice; fluid tightrope |
| Doris | **HIGH** | 13 | 11 | Same dementia diagnosis as Pat; 5× more interactions |
| Sylvia | **HIGH** | 11 | 10 | Body warning signs (sweat, heat sensation) switched off |
| Elsie | HIGH | 13 | 4 | Lithium toxicity; cannot self-report early tremor |
| Iris | HIGH | 12 | 4 | Silent multi-organ failure; cannot sweat or self-rescue |
| Alan | Elevated | 3 | 3 | Same cardiovascular diagnosis as Victor; fraction of the risk |
| Pat | Elevated | 2 | 2 | Same dementia diagnosis as Doris; caregiver present |
| Ben | Elevated | 5 | 5 | Low score — insulin storage failure is life-critical |

**The demo move:** select Victor → High, 14 plan items, "drink plenty" inverted.
Then select Alan → Elevated, 3 plan items, standard advice.
Same GP diagnosis. Same weather. Completely different plan.

---

## Monitoring dashboard (/monitoring)

Served from `/api/monitoring` and `/api/series/[id]`, over the three days of
Episode 4 rather than the peak alone — the argument is about lead time. Shows
the national picture on 19 July 2025:
- **146** excess deaths (UKHSA Episode 4)
- **0** regional heat-health alerts issued
- **5/8** demo profiles at HIGH risk when assessed individually
- The national cascade (UKHSA → NHS England → ICBs → providers) issued nothing

Source: UKHSA *Heat mortality monitoring report, England: 2025* (Crown copyright, OGL v3).

---

## Keeping servers running after disconnect

Use `screen` or `tmux` to keep processes alive when the terminal closes:

```bash
# Start a named session
tmux new -s climatise

# Inside tmux: start both servers
uv run uvicorn api.main:app --port 8000 --log-level warning &
cd web/app && npm start -- --port 3000 &
cloudflared tunnel --url http://localhost:3000 &

# Detach: Ctrl-b d
# Reattach: tmux attach -t climatise
```

---

## Pulling updates

```bash
git pull origin main

# Rebuild the frontend
cd web/app && npm install && npm run build

# Restart the Python API (picks up new code automatically with --reload in dev)
# In production: kill and restart uvicorn

# Restart Next.js prod server
lsof -ti:3000 | xargs kill -9
npm start -- --port 3000 > /tmp/next.log 2>&1 &
```
