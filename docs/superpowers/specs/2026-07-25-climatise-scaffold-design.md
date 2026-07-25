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
| Org layer | Multi-tenant data model, council tenant type only |
| Team shape | Two contributor tracks over a pre-built green core |

### Deviations from the source spec

Both are deliberate and both are narrower than they first appear.

**§14 lists multi-tenant management as out of scope for v0.1.** We build the tenancy
*data model* now because retrofitting `org_id` scoping onto an existing assessment table
is the expensive mistake, while declaring three unused tenant-type enum values is free.
Only `COUNCIL` is implemented. There is no identity-provider integration and no
self-serve tenant onboarding, so SC-6 is not crossed: every org and cohort in the build
is fictional and seeded.

**Resource allocation is not in the source spec at all.** It sits above L5 as
`packages/allocation/` and is pure in the same sense L3 is, so it adds no new
persistence and no new failure modes on the read path.

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
│   ├── resources/          L5 seeded resource lookup
│   ├── allocation/         resource allocation — ranking, coverage, siting
│   └── org/                L6 tenancy, cohorts, aggregate queries
├── services/
│   ├── api/                FastAPI. Routing, serialisation, auth stub only.
│   └── scheduler/          the 3-hourly loop (§5.3)
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
class ExposureFeatures:          # L1 → L3. The only thing L3 knows about weather.
    date: date
    overnight_min: float
    peak_apparent: float
    peak_air: float
    hours_above_26: int
    indoor_night_est: float      # modelled — SC-5
    indoor_day_est: float        # modelled — SC-5
    spell_day: int
    alert_level: AlertLevel      # includes NOT_CHECKED per FR-12
    source: ExposureSource       # LIVE | ARCHIVE | CACHE — provenance, not a mode switch

@dataclass(frozen=True, slots=True)
class Reason:
    code: ReasonCode
    title: str
    explanation: str
    weight: int

@dataclass(frozen=True, slots=True)
class Assessment:                # L3 → everything downstream
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
    p_onset: float             # P(episode threshold met), from ensemble member fraction
    expected_peak: float
    expected_duration_days: int
    ensemble_spread: float     # model disagreement, i.e. confidence
    lead_time_hours: int       # the number a council actually acts on
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

## 6. Allocation

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

## 7. Multi-tenant, council-first

```sql
org(id, name, type, area_codes)        -- COUNCIL implemented; CARE_HOME, ICB, HOSPITAL declared
cohort(id, org_id, name)
cohort_member(cohort_id, person_id, consent_basis)
org_member(org_id, user_id, role)
```

Every L6 query is scoped by `org_id` and `area_codes` from the first commit.
`consent_basis` is `NOT NULL`, so SC-6 is structurally enforced rather than remembered.

The council view is one page: tier distribution across the cohort filterable by ward,
tomorrow's `rank_visits` output, and the current `coverage_gap`. All of it remains pure
queries over the `assessment` table, introducing no new persistence (AC-4).

---

## 8. Web

Three surfaces over one `web/shared/`. Tier is never conveyed by colour alone (NFR-07),
so a tier badge is a shared component rendering text, shape and colour together — not a
CSS class each surface reimplements.

- **`companion/`** — new PWA. Usable at 360 px, body text ≥16 px, tap targets ≥44 px
  (NFR-05, NFR-06). Offline-first: a service worker caches the last assessment so the app
  renders a complete result with no network (NFR-04). The §9.1 escalation ladder renders
  progressively — rung *n+1* is not present in the DOM until rung *n* has been presented.
- **`national/`** — the existing prototype, retained, plus a live mode reading real
  aggregates alongside the 2025 replay.
- **`explorer/`** — the existing prototype, with the seeded RNG in `buildFacilities()`
  replaced by the L5 resource table and a coverage-gap overlay drawn on top.

---

## 9. Verification

`tests/verification/` carries one file per row of §13. Three gate merges:

| File | Gate |
|---|---|
| `test_worked_example.py` | Doris, 19 July 2025, Bedford → risk 6.0, tier HIGH, exact reason set (§8.6) |
| `test_no_cry_wolf.py` | Low-vulnerability persona over the 92-day replay returns Low on every day |
| `test_safety_corpus.py` | Action corpus contains no *stop · reduce · skip · halt · delay · alter* in any medication context. Zero matches or the build fails (SC-1) |

Plus discrimination (three personas, identical conditions, ≥2 distinct tiers), historical
validity (Episode 4 replay returns High or above with no regional alert), and the NFR-04
network-down render.

CI additionally runs the ruff complexity gate — `C901` max-complexity 10, `PLR0915`
max-statements 50 — as a complexity-only ruleset.

---

## 10. Track split

Three contributors, three owned tracks.

| Track | Owner | Owns | Seam |
|---|---|---|---|
| **0 — Core + data sources** | person 1 | `contracts/`, `core/`, `exposure/`, `persons/`, `resources/`, `services/api/`, seed data, CI | defines `ExposureFeatures` and `Assessment` |
| **A — Companion** | person 2 | `actions/`, `web/companion/` | consumes `Assessment` |
| **B — Predictor + council** | person 3 | `predictors/`, `allocation/`, `org/`, `web/national/`, `web/explorer/` | produces `ExposureFeatures`, consumes `Assessment` |

Tracks A and B meet `assess()` from opposite sides and never write to the same directory.

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

## 11. Deferred

Recorded so they are visible rather than rediscovered.

| Item | Why deferred | Where noted |
|---|---|---|
| Isochrone distances | Haversine is adequate for one locality | `allocation/distance.py` TODO |
| `LearnedIndoor` regression | Needs sensor data that does not exist yet; FR-11 analytic form is the baseline | `predictors/indoor.py` stub |
| Cold-side parity | §12 notes cold mortality lags 1–2 weeks; alerting-shaped design is wrong for it | `predictors/cold_lag.py` stub |
| Care home / ICB / hospital tenants | Enum values declared, no implementation | `org/models.py` |
| SMS dispatch | v0.2 per §15 | `actions/notify.py` |
| Pharmacist review of medication rules | SC-4 — demonstrator only until done | `README.md`, prominent |

---

## 12. Open risks

**The ensemble predictor is the schedule risk.** A probabilistic model with a backtest is
a full day of work for one person. `ThresholdHeatwave` shipping green is the mitigation;
if the ensemble does not land, the chain still runs and the lead-time claim becomes
deterministic rather than probabilistic.

**Indoor temperature remains the dominant error term** at ±3–5 °C, and no part of this
design fixes that — it is a sensor problem (v0.3). Every displayed indoor figure is
labelled modelled (SC-5), and tier boundaries should be read as uncertain at the margin.

**The weighting scheme is expert judgement, not empirically fitted.** Tiers rather than
point estimates, documented as a demonstrator, unusable with real patients until SC-4 is
satisfied.
