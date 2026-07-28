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

## Vercel

Two projects from this one repository. They are separate because they run on
different runtimes, not because the code is split — the web tier calls the core
server-side and never exposes it to the browser.

| Project | Root Directory | Preset | Serves |
|---|---|---|---|
| `climatise-core` | `./` | Python | The FastAPI risk engine |
| `climatise-web` | `web/app` | Next.js | The app people open |

**Deploy the core first** — the web project needs its URL.

`app.py` is the entrypoint. It exists because Vercel's Python preset runs
`pip install -r requirements.txt`, and pip cannot resolve the thirteen workspace
members that reference each other through uv's `{ workspace = true }`. It does
not have to: Vercel bundles every project file, so the packages are already
there and only need to be importable. `app.py` adds each `src` to `sys.path`.
`requirements.txt` therefore lists third-party dependencies only, pinned to the
versions `uv.lock` already resolved.

### Environment variables

On `climatise-core`:

| Variable | Why |
|---|---|
| `CLIMATISE_PUSH_TOKEN` | Required before `/push/subscribe` will accept anything. Without it registration returns 503 — it fails closed, because an open endpoint lets a stranger point their own phone at a named person's alerts. |
| `CRON_SECRET` | Vercel generates and sends this. Without it `/cron/sweep` returns 503. |
| `KV_REST_API_URL`, `KV_REST_API_TOKEN` | Injected by the Upstash integration. Without them the stores fall back to a local file, which on serverless means every invocation starts empty. |
| `TWILIO_*` | Only needed if the sweep should actually send. |

On `climatise-web`: `CORE_API_URL` set to the core project's URL, plus the
`NEXT_PUBLIC_VAPID_PUBLIC_KEY` and `ANTHROPIC_API_KEY` from the table below.

### Storage

`vercel install upstash`, then attach it to `climatise-core`. Serverless has no
writable filesystem that survives an invocation, so without this the check-in
log and the push subscriptions are empty on every request — the feature appears
to work and silently keeps nothing.

### The sweep

`vercel.json` schedules `/cron/sweep` daily at 07:00. **Hobby accounts cannot
run cron more than once per day, and fire anywhere within the hour.** The design
assumes a three-hourly pass, so a Hobby deployment samples the day once rather
than eight times: a risk that rises after the morning sweep waits until
tomorrow. Pro lifts this to per-minute.

The endpoint does **not** send unless asked — `POST /cron/sweep?send=true`. The
default is a dry run for the same reason the CLI's is: otherwise the first
person to curl it messages five people.

### What is unverified

The image has never been built here and the deployment has never run. Three
things can only be confirmed on a first deploy:

- Whether the bundle stays under the 250 MB limit
- Whether `parents[4]` still resolves to the project root inside the function,
  which is how `persons.loader` finds the persona corpus
- Whether cold-start latency is tolerable, given the core loads the corpus, the
  interaction table and every persona at import

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
| `/companion` | Caregiver view | Caregiver | Escalation routes prominent; Watch-fors prominent |
| `/monitoring` | Population dashboard | — | Cohort risk across the three days of the episode, plus the UK choropleth |
| `/onboarding` | Set up a profile | — | Collects name, postcode, conditions, meds |

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

| Profile | Tier | Vuln | Plan items | Demo argument |
|---|---|---|---|---|
| Victor | **HIGH** | 18 | 16 | "Drink plenty" is the wrong advice; fluid tightrope |
| Doris | **HIGH** | 15 | 12 | Same dementia diagnosis as Pat; 5× more interactions |
| Sylvia | **HIGH** | 11 | 10 | Body warning signs (sweat, heat sensation) switched off |
| Elsie | HIGH | 13 | 10 | Lithium toxicity; cannot self-report early tremor |
| Iris | HIGH | 12 | 10 | Silent multi-organ failure; cannot sweat or self-rescue |
| Alan | Elevated | 3 | 3 | Same cardiovascular diagnosis as Victor; fraction of the risk |
| Pat | Elevated | 2 | 2 | Same dementia diagnosis as Doris; caregiver present |
| Ben | Elevated | 5 | 5 | Low score — insulin storage failure is life-critical |

**The demo move:** select Victor → High, 16 plan items, "drink plenty" inverted.
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
