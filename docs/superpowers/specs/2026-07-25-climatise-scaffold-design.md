# Climatise / Climate Companion — scaffold design

**Date:** 2026-07-25
**Source spec:** Climate Companion System Specification v0.1
**Status:** approved for implementation
**Contributors:** 3 (one core + data sources, one companion app, one predictor + council view)

---

## 1. What this scaffold is for

The source spec defines seven layers (L0–L6) and stops at "the caregiver acts". This
scaffold extends that chain by one link and organises the whole thing so three people
can build it in parallel without waiting on each other:

```
predict the heatwave  →  assess the individual  →  allocate scarce capacity  →  act
   (lead time)             (risk tier)              (preparation)              (response)
```

Resource allocation is the addition. It is what converts a per-person risk tier into a
council deployment decision, and it is what makes the probabilistic predictor
load-bearing rather than decorative — a council needs roughly 72 hours to open a cool
space, so a probability at day-5 is worth more to them than certainty at day-0.

### Decisions taken

| Decision | Choice |
|---|---|
| Stack | Python 3.13 + uv workspace, pure-Python core, FastAPI service, static/PWA front end |
| Handoff model | Contract-first — frozen types and a red test suite; core ships green |
| Predictor layer | Yes, as an L1.5 seam behind a Protocol; heatwave forecasting is first-class |
| Org layer | Multi-tenant data model; council and hospital tenant types implemented |
| Companion users | Both the cared-for person (voice check-in) and the caregiver (app) |
| Team shape | Three owned tracks over a frozen contracts layer |

### Deviations from the source spec

Both are deliberate and both are narrower than they first appear.

**§14 lists multi-tenant management as out of scope for v0.1.** We build the tenancy
*data model* now because retrofitting `org_id` scoping onto an existing assessment table
is the expensive mistake, while declaring unused tenant-type enum values is free.
`COUNCIL` and `HOSPITAL` are implemented; `CARE_HOME` and `ICB` are declared only. There
is no identity-provider integration and no self-serve tenant onboarding, so SC-6 is not
crossed: every org and cohort in the build is fictional and seeded.

**Resource allocation is not in the source spec at all.** It sits above L5 as
`packages/allocation/` and is pure in the same sense L3 is, so it adds no new
persistence and no new failure modes on the read path.

**The cared-for person becomes a direct user.** §1.3 defines them as "not necessarily a
user of the system" and §3 lists the caregiver as primary. We invert this: the cared-for
person receives scheduled voice check-ins, and the caregiver keeps the app. The
justification is that NFR-05 and NFR-06 — 360 px layouts, ≥16 px text, ≥44 px targets —
are mitigations for a modality that is a poor fit for an 85-year-old with presbyopia and
limited dexterity. Voice removes the problem instead of mitigating it, and it reaches
people who own no smartphone at all.

This is the largest safety change in the design and it is governed by §6 below.

---

## 2. Repository layout

```
climatise/
├── packages/
│   ├── contracts/          frozen dataclasses + enums. Zero dependencies.
│   ├── core/               L2 vulnerability · L3 fusion. Pure: no I/O, no clock.
│   ├── predictors/         L1.5 seam — Predictor Protocol + heatwave/indoor models
│   ├── exposure/           L1 Open-Meteo client, normalisation, on-disk cache
│   ├── persons/            L0 postcodes.io, dwelling offsets, persona loader
│   ├── actions/            L4 reason_code → checklist, escalation, notify policy
│   ├── checkin/            voice check-in — scripting, dispatch, response capture
│   ├── resources/          L5 seeded resource lookup
│   ├── allocation/         resource allocation — ranking, coverage, siting
│   └── org/                L6 tenancy, cohorts, aggregate queries
├── services/
│   ├── api/                FastAPI. Routing, serialisation, auth stub only.
│   ├── scheduler/          the 3-hourly loop (§5.3) and check-in scheduling
│   └── voice/              telephony webhook handler
├── web/
│   ├── shared/             tier vocabulary, offline shell
│   ├── companion/          caregiver PWA
│   ├── national/           national view — existing prototype, wired
│   └── explorer/           geographic explorer — existing prototype, wired
├── data/seed/              personas · med classes · actions · dwelling offsets · resources · orgs
├── tests/                  mirrors packages/, plus tests/verification/ for §13
└── docs/
```

Each `packages/*` is a uv workspace member with its own `pyproject.toml`. This is what
makes parallel contribution safe: a contributor owns a directory and a test file, and the
import graph physically prevents them reaching sideways into someone else's work.

---

## 3. Contracts — the coordination mechanism

`packages/contracts/` ships complete and green before anyone starts. It is the only
module every track reads, and nothing else in the repository defines a type that crosses
a layer boundary.

```python
@dataclass(frozen=True, slots=True)
class ExposureFeatures:  # L1 → L3. The only thing L3 knows about weather.
    date: date
    overnight_min: float
    peak_apparent: float
    peak_air: float
    hours_above_26: int
    indoor_night_est: float  # modelled — SC-5
    indoor_day_est: float  # modelled — SC-5
    spell_day: int
    alert_level: AlertLevel  # includes NOT_CHECKED per FR-12
    source: ExposureSource  # LIVE | ARCHIVE | CACHE — provenance, not a mode switch


@dataclass(frozen=True, slots=True)
class Reason:
    code: ReasonCode
    title: str
    explanation: str
    weight: int


@dataclass(frozen=True, slots=True)
class Assessment:  # L3 → everything downstream
    tier: Tier
    risk_score: float
    exposure_score: int
    vulnerability_score: int
    reasons: tuple[Reason, ...]  # AC-2: nothing downstream re-derives from raw exposure
```

Two pure signatures carry the entire system:

```python
def profile(person: Person) -> VulnerabilityProfile                      # L2
def assess(exposure: ExposureFeatures,
           vulnerability: VulnerabilityProfile) -> Assessment            # L3 — AC-1
```

No `datetime.now()`, no session, no config object, no mode flag. `assess` is callable
from a bare REPL. AC-5 (one implementation for live and replay) and NFR-04 (works with no
network) then fall out of the signature rather than needing branching to support them.

`ExposureSource` records where the numbers came from; it never changes behaviour.

---

## 4. L2 and L3 — the core

Table-driven rather than branching. `EXPOSURE_RULES` and `VULNERABILITY_RULES` are tuples
of `(ReasonCode, predicate, weight)` transcribed directly from §8.1 and §8.2, so adding a
rule is a data edit and the tables are diffable line-by-line against the spec during
review. Fusion is the four lines of §8.4.

FR-18's short-circuit (`exposure_score == 0 → Tier.LOW`) is written explicitly and tested
separately from the fusion arithmetic, because it is the rule that stops a frail person
sitting permanently at Elevated and destroying the signal.

Reason titles and explanations live in `data/seed/reasons.yaml`, not in Python. AC-3 —
every reason code maps to at least one action — becomes a startup assertion and a test,
so a code with no action fails CI instead of shipping as a silent specification defect.

---

## 5. Predictors — heatwave forecasting as the lead-time engine

```
packages/predictors/
├── base.py           Predictor Protocol
├── heatwave.py       episode onset and severity, probabilistic, 14-day horizon
├── indoor.py         FR-11 analytic baseline  +  LearnedIndoor stub
├── cold_lag.py       §12 1–2 week lag tracker
└── backtest.py       §13 replay harness over the 92-day 2025 season
```

`heatwave.py` is the substantial piece. Open-Meteo exposes an ensemble endpoint carrying
ICON, GFS and ECMWF members, so the honest model is member-fraction over threshold rather
than a point forecast:

```python
@dataclass(frozen=True, slots=True)
class EpisodeForecast:
    horizon_days: int
    p_onset: float  # P(episode threshold met), from ensemble member fraction
    expected_peak: float
    expected_duration_days: int
    ensemble_spread: float  # model disagreement, i.e. confidence
    lead_time_hours: int  # the number a council actually acts on
```

The episode threshold matches the UKHSA definition already encoded in the national-view
prototype's `EPISODES` array, which gives the backtest real ground truth. The headline
question it answers: **would this model have flagged Episode 4 — 17–19 July 2025, where
UKHSA issued no alert in any region and an estimated 146 people died — at 72 hours or
more of lead time?** That is falsifiable, and it is the strongest claim the project can
make.

SC-7 applies directly. `p_onset` triggers preparation at a deliberately low threshold; the
chosen value is documented as an over-warn bias and reported alongside its false-positive
rate from the backtest.

**Fallback.** `ThresholdHeatwave` — a deterministic threshold-crossing detector emitting
`p_onset ∈ {0, 1}` — is seeded green by the scaffold and owned by Track B thereafter. The
chain therefore works end-to-end from hour one, and the ensemble model upgrades it in
place behind the same Protocol. This is the single largest schedule risk in the build and
this is its mitigation.

**L3 never imports this package.** Predictors produce `ExposureFeatures`; `assess()` sees
only the dataclass. The seam holds in the import graph, not by convention.

---

## 6. Voice check-in — the cared-for person as user

A scheduled outbound call during a risk window, to the person themselves. Three jobs, in
priority order: **confirm they are alright**, **deliver the two or three actions that
matter tonight**, and **capture what the model cannot see**.

### The safety constraint that shapes everything else

SC-1 forbids advising any change to a prescribed medication. Static text passes that gate
by being greppable; a generative voice agent does not. The design constraint is therefore
absolute:

> **The check-in selects utterances from the action corpus. It never composes them.**

Every line the caller hears is a row that has already passed `test_safety_corpus.py`. The
agent chooses which rows to read, in what order, based on the reason codes on the current
`Assessment`. It cannot say something novel about a medicine because it cannot compose
novel sentences at all. Speech recognition maps replies onto a closed response set; an
unrecognised reply is treated as no-answer, never as free text to be interpreted.

This costs conversational range and buys a system that is auditable line by line. For a
tool speaking unsupervised to an 88-year-old about their health, that is the correct
trade.

### What comes back

```python
@dataclass(frozen=True, slots=True)
class SelfReport:
    person_id: str
    window: DateRange
    answered: bool
    bedroom_feels_hot: bool | None  # corrects the modelled indoor estimate
    drinking_fluids: bool | None
    red_flags: tuple[RedFlag, ...]  # SC-3 set only
    transcript_ref: str | None  # pointer, not content
```

Two distinct paths, and keeping them distinct is what preserves L3:

**Self-report corrects exposure at L1.** §12 names modelled indoor temperature as the
dominant error term at ±3–5 °C, with a sensor in v0.3 as the fix. Asking *"is your bedroom
uncomfortably warm tonight?"* is a cheap partial substitute available now. A positive
answer raises `indoor_night_est` toward the `BEDROOM_UNSAFE` boundary and sets
`ExposureSource.SELF_REPORT`. The correction is bounded and documented, and it is still
labelled modelled (SC-5) because it remains an estimate.

**Red flags and no-answer escalate at L4.** They never enter risk fusion. The weather has
not become more dangerous because a phone went unanswered — but what to *do* has changed.
So `assess()`'s signature is untouched, L3 stays exactly as the source spec defines it,
and the whole voice layer sits outside the pure core.

### No answer is the signal

A missed call during a Severe window is precisely the condition this system exists to
catch, so it is an escalation trigger rather than a retry loop: caregiver notified
immediately, then rung 6 — council welfare check — if the caregiver does not acknowledge.
Under SC-7's over-warn bias, unreachable is treated as unwell until someone confirms
otherwise.

Red flags are the SC-3 set only — unrousable, confusion, cessation of urine output, hot
dry skin without sweating — and only these route to 999.

### Provider

`VoiceChannel` Protocol with two implementations: `ConsoleVoice`, which prints the
transcript and reads stdin, and a telephony provider behind the same interface.
`ConsoleVoice` ships green, so the entire flow is testable and demoable with no telephony
account, no phone number and no per-minute cost.

### Consent and data

A voice recording of a vulnerable person is health data and plausibly biometric, so this
layer raises the SC-6 stakes sharply. Three rules hold in the build: calls are placed only
to seeded fictional personas; `SelfReport` stores a `transcript_ref` rather than transcript
content; and `cohort_member.consent_basis` gates check-in scheduling, not merely
reporting. Recording real voices is out of scope until the DPIA in §15 v1.0 is complete.

---

## 7. Allocation

Pure functions over `(assessments, resources, capacity) → AllocationPlan`, in the same
style as L3. Three questions, one function each:

| Function | Question | Output |
|---|---|---|
| `rank_visits` | "We have 40 welfare checks tomorrow. Who?" | Ordered persons, each carrying the reason codes justifying its position |
| `coverage_gap` | "Who is Severe-tier and beyond reach of any cool space?" | Uncovered cohort plus the gap geometry |
| `siting_delta` | "If we open the library, how many more are covered?" | Marginal coverage per candidate site |

Ranking is `tier × isolation × reachability`, not raw risk score. A Severe-tier person
with a live-in carer ranks below a High-tier person living alone, because allocation
optimises **harm averted per visit** rather than risk observed. That distinction is the
intellectual content of the layer and it gets its own test file.

Because the layer is pure it replays over historical seasons, which makes "here is what
optimal deployment on 17 July 2025 would have looked like" a runnable demo rather than an
assertion.

**Distance.** Straight-line haversine ships in the scaffold. Real isochrones — an
82-year-old's 800 metres is not a 40-year-old's — are recorded as a v0.2 note, not a
hackathon task.

---

## 8. Multi-tenant — council, hospital and care home

```sql
org(id, name, type, area_codes)   -- COUNCIL, HOSPITAL, CARE_HOME implemented; ICB declared
cohort(id, org_id, name)
cohort_member(cohort_id, person_id, consent_basis)
org_member(org_id, user_id, role)
```

Every L6 query is scoped by `org_id` and `area_codes` from the first commit.
`consent_basis` is `NOT NULL`, so SC-6 is structurally enforced rather than remembered.

Three views, all pure queries over the `assessment` table, introducing no new persistence
(AC-4). They differ only in how they aggregate, which is the whole point of AC-4 — a new
stakeholder is a new query, not a new system.

**Council** — tier distribution across the cohort filterable by ward, tomorrow's
`rank_visits` output, and the current `coverage_gap`. Answers *where do I send people
tomorrow*.

**Hospital** — surge forecast. `EpisodeForecast × cohort vulnerability distribution`
projected over the predictor's 14-day horizon, giving expected presentations by day with
the ensemble spread carried through as a confidence band. Answers *how many beds, and
when*. Both inputs already exist for Track B, so this is an aggregation rather than new
machinery.

**Care home** — a resident board: every resident on one screen, sorted by tier, with the
reason codes that put them there and tonight's checklist per resident. Answers *which of
my forty residents tonight*.

The care home is the sharpest case of the three, and the evidence in §2.2 is why. Care
homes already sit **inside** the UKHSA cascade — they receive the alerts. Yet 677 of the
1,504 heat-associated deaths in summer 2025 were in care homes, and Episode 4 was
statistically significant in care homes specifically. The failure there is not that the
alert fails to arrive; it is that a building-level alert cannot say which resident is the
one at risk tonight. Per-resident tiering is the missing granularity, and it is a filter
over data the system already holds.

This also reframes the product argument. The unpaid-carer gap in §2.3 is a *distribution*
problem with no register to solve it; the care home gap is a *resolution* problem inside
an existing, funded, regulated channel. The second is materially easier to sell.

The projection is explicitly a demonstrator: it is expert-judgement weighting propagated
forward, not an epidemiological model, and it is labelled as such wherever displayed.
§12.2 already concedes the weighting scheme is not empirically fitted, and projecting it
into admissions compounds that. It shows *shape and timing*, not a number to staff
against.

---

## 9. Web

Four surfaces over one `web/shared/`. Tier is never conveyed by colour alone (NFR-07), so
a tier badge is a shared component rendering text, shape and colour together — not a CSS
class each surface reimplements.

- **`companion/`** — caregiver PWA. Usable at 360 px, body text ≥16 px, tap targets ≥44 px
  (NFR-05, NFR-06). Offline-first: a service worker caches the last assessment so the app
  renders a complete result with no network (NFR-04). The §9.1 escalation ladder renders
  progressively — rung *n+1* is not present in the DOM until rung *n* has been presented.
  Shows the outcome of the most recent voice check-in, including an unanswered one.
- **`org/`** — the three tenant views of §8. One shell, three aggregations, tenant type
  selecting which is mounted.
- **`national/`** — the existing prototype, retained, plus a live mode reading real
  aggregates alongside the 2025 replay.
- **`explorer/`** — the existing prototype, with the seeded RNG in `buildFacilities()`
  replaced by the L5 resource table and a coverage-gap overlay drawn on top.

The cared-for person has no web surface at all. Their interface is the phone call.

---

## 10. Verification

`tests/verification/` carries one file per row of §13. Four gate merges:

| File | Gate |
|---|---|
| `test_worked_example.py` | Doris, 19 July 2025, Bedford → risk 6.0, tier HIGH, exact reason set (§8.6) |
| `test_no_cry_wolf.py` | Low-vulnerability persona over the 92-day replay returns Low on every day |
| `test_safety_corpus.py` | Action corpus contains no *stop · reduce · skip · halt · delay · alter* in any medication context. Zero matches or the build fails (SC-1) |
| `test_voice_utterances.py` | Every utterance the voice agent can emit resolves to a row in the action corpus. Any unsourced string fails the build (§6) |

The fourth is what makes §6's constraint enforceable rather than aspirational: it asserts
the closed utterance set, so the agent cannot acquire the ability to compose a sentence
without a test going red.

Plus discrimination (three personas, identical conditions, ≥2 distinct tiers), historical
validity (Episode 4 replay returns High or above with no regional alert), no-answer
escalation (unanswered Severe-window call raises rung 6 within policy), and the NFR-04
network-down render.

CI additionally runs the ruff complexity gate — `C901` max-complexity 10, `PLR0915`
max-statements 50 — as a complexity-only ruleset.

---

## 11. Track split

Three contributors, three owned tracks.

| Track | Owner | Owns | Seam |
|---|---|---|---|
| **0 — Core + data sources** | person 1 | `contracts/`, `core/`, `exposure/`, `persons/`, `resources/`, `services/api/`, seed data, CI | defines `ExposureFeatures` and `Assessment` |
| **A — Companion + voice** | person 2 | `actions/`, `checkin/`, `services/voice/`, `web/companion/` | consumes `Assessment`, emits `SelfReport` |
| **B — Predictor + org views** | person 3 | `predictors/`, `allocation/`, `org/`, `web/org/`, `web/national/`, `web/explorer/` | produces `ExposureFeatures`, consumes `Assessment` |

Tracks A and B meet `assess()` from opposite sides and never write to the same directory.
`SelfReport` crosses from A back into Track 0's `exposure/` as an indoor correction, so it
is defined in `contracts/` and frozen with everything else before either track starts.

### Data contribution surfaces

Two further surfaces take contributors without allocating them a code track, and they
scale to as many people as are available:

| Surface | Directory | Adds |
|---|---|---|
| **Profiles** | `data/personas/*.yaml` | One file per cared-for person — age band, conditions, medications, dwelling, isolation |
| **Geography** | `data/geography/*.yaml` | Regions, wards, dwelling offsets, cool spaces, pharmacies, warm banks |

The property that makes these work: **adding a file must never require editing Python.**
Loaders glob the directory, a schema validates each file, and CI fails on an invalid file
with a readable error naming the file and field. A contributor adding their fifteenth
persona touches no module anyone else owns, so these surfaces never serialise behind a
code track.

They are also load-bearing rather than busywork. Persona breadth is what makes the §13
discrimination test meaningful — three personas is the stated minimum, not a target — and
geographic detail is what makes `coverage_gap` and `siting_delta` produce a demo worth
watching rather than a function with two rows of input.

**Interface first, then data.** The scaffold freezes `contracts/` and ships `core/` green
on day zero, with every data source behind it backed by fixtures rather than network
calls. Tracks A and B can therefore start against real types and real assessments in hour
one, while Track 0 replaces each fixture-backed source with its live client — Open-Meteo
forecast and archive, postcodes.io, the UKHSA dashboard — behind the unchanged interface.

This is the property worth protecting: **swapping a data source must never be visible to
A or B.** It holds because `ExposureFeatures` carries a `source` field that records
provenance without changing behaviour, so a fixture, a cache hit and a live call are
indistinguishable to `assess()`. Consequently a data source landing late costs lead-time
accuracy, never a downstream rewrite.

`CONTRIBUTING.md` carries this table with a "tests to green" column naming the exact test
files each track must turn.

---

## 12. Deferred

Recorded so they are visible rather than rediscovered.

| Item | Why deferred | Where noted |
|---|---|---|
| Isochrone distances | Haversine is adequate for one locality | `allocation/distance.py` TODO |
| `LearnedIndoor` regression | Needs sensor data that does not exist yet; FR-11 analytic form is the baseline | `predictors/indoor.py` stub |
| Cold-side parity | §12 notes cold mortality lags 1–2 weeks; alerting-shaped design is wrong for it | `predictors/cold_lag.py` stub |
| ICB tenant | Enum value declared, no implementation | `org/models.py` |
| Live telephony | `ConsoleVoice` covers the demo; real calls need consent and a DPIA | `services/voice/` |
| Voice recording retention | Health and plausibly biometric data; `transcript_ref` only until DPIA | `checkin/models.py` |
| SMS dispatch | v0.2 per §15 | `actions/notify.py` |
| Pharmacist review of medication rules | SC-4 — demonstrator only until done | `README.md`, prominent |

---

## 13. Open risks

**The ensemble predictor is the schedule risk.** A probabilistic model with a backtest is
a full day of work for one person. `ThresholdHeatwave` shipping green is the mitigation;
if the ensemble does not land, the chain still runs and the lead-time claim becomes
deterministic rather than probabilistic.

**Indoor temperature remains the dominant error term** at ±3–5 °C, and no part of this
design fixes that — it is a sensor problem (v0.3). Every displayed indoor figure is
labelled modelled (SC-5), and tier boundaries should be read as uncertain at the margin.

**The weighting scheme is expert judgement, not empirically fitted.** Tiers rather than
point estimates, documented as a demonstrator, unusable with real patients until SC-4 is
satisfied. The hospital surge view in §8 propagates this uncertainty furthest and is
labelled accordingly.

**Track A now carries two products.** A caregiver PWA and an unsupervised voice agent are
each a full track, and they landed on one person. The voice layer is the one that must not
be rushed, because it is the only component that speaks unsupervised to a vulnerable
person. If the track is over capacity, the correct cut is the PWA — check-in plus SMS to
the caregiver delivers the safety function without it, whereas a half-built voice agent
does not degrade safely. Decide this early rather than at the code freeze.
