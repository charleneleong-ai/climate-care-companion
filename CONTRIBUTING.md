# Contributing

Five contribution surfaces. Three are code tracks; two are data directories that
need no Python at all.

## Setup

```bash
uv sync --all-packages
uv run pytest              # everything
uv run pytest tests/verification -v   # just the merge gates
uv run pre-commit install
```

## Code tracks

Each track owns directories nobody else writes to. Pick one, turn its tests green.

| Track | Owns | Tests to turn green |
|---|---|---|
| **0 — Core + data sources** | `packages/contracts` `packages/core` `packages/exposure` `packages/persons` `packages/geography` `services/api` | Already green. Keep it that way, then replace the fixture-backed sources with live Open-Meteo and postcodes.io clients. |
| **A — Companion + voice** | `packages/actions` `packages/checkin` `services/voice` `web/companion` | `tests/stubs::ChecklistBuilder.build` · `::NotificationPolicy.should_notify` |
| **B — Predictor + org views** | `packages/predictors` `packages/allocation` `packages/org` `web/org` `web/national` `web/explorer` | `tests/stubs::CouncilView.render` · `::HospitalView.render` · `::CareHomeView.render` · `::ColdLagTracker.track` · `::SeasonBacktest.run` · `test_ensemble_predictor_stub_names_track_b` |

Tracks A and B meet `RiskScorer.assess()` from opposite sides and never write to
the same directory.

### Track A's first job — the corpus is in the wrong voice

`data/seed/actions.csv` is written in the third person, for the caregiver: *"they
may not feel like drinking"*, *"offer fluids regularly"*. But the check-in calls the
cared-for person, and
[`CheckinScript`](packages/checkin/src/checkin/script.py) reads those rows verbatim.
Spoken to an 88-year-old they are wrong, and in the dementia case actively
confusing.

The fix is a second person-facing text column plus selection logic — not a rewrite
of the existing column, which the caregiver PWA still needs. Until it lands, treat
the voice path as a scaffold rather than a script.

### Track 0's first job

Everything downstream currently runs against `FIXTURE_EXPOSURE` in
[`services/api/src/api/main.py`](services/api/src/api/main.py). Replacing it with a
live Open-Meteo client must be invisible to Tracks A and B — `ExposureFeatures`
carries a `source` field recording provenance without changing behaviour, so a
fixture, a cache hit and a live call are indistinguishable to the scoring core.

If that property ever breaks, the tracks stop being independent.

## Data surfaces — no Python required

Drop a file in, run the tests, open a PR. These scale to as many contributors as
are available and never queue behind a code track.

### Add a profile — `data/personas/<name>.yaml`

```yaml
id: albert
name: Albert
age_band: b85_plus        # under_65 | b65_74 | b75_84 | b85_plus
lives_alone: true
mobility_limited: true
conditions: [renal, respiratory]
medications:
  - drug_name: furosemide
    drug_class: diuretic  # see data/seed/med_classes.csv
place:
  postcode: MK40 2CD
  dwelling_type: flat     # house | flat | bungalow | care_home
  floor: 4
  aspect: south
  has_cooling: false
  heating_affordable: false
```

Persona breadth is load-bearing, not busywork: `tests/data` asserts that at least
two distinct tiers appear across the persona set under identical weather. Three
personas is the stated minimum in the spec, not a target.

### Add geography — `data/geography/<locality>.yaml`

```yaml
name: Luton
region: East of England
admin_district: Luton
wards: [Biscot, Dallow, High Town]
resources:
  - id: lut-cool-01
    type: cool_space      # cool_space | pharmacy | warm_bank | council_welfare
    name: Luton Central Library
    lat: 51.8787
    lon: -0.4200
    opening_hours: "Mon-Sat 09:00-17:00"
    area_code: E06000032
```

Geographic detail is what makes `coverage_gap` and `siting_delta` produce a demo
worth watching rather than a function with two rows of input.

An invalid file fails CI with a message naming the file and the field. You do not
need to touch a loader.

## House rules

- **The four merge gates in `tests/verification/` must never go red.** They are the
  §8.6 worked example, no-cry-wolf across 92 days, the SC-1 medication safety grep,
  and the closed voice utterance set.
- **Never advise altering a prescribed medication** (SC-1). State the risk, route to
  a pharmacist or GP. The gate greps for *stop · reduce · skip · halt · delay ·
  alter · discontinue · lower* in any medication row.
- **The voice agent selects, it never composes.** Every utterance must be a row in
  `data/seed/actions.csv`. Adding a string the agent can say without adding it to
  the corpus turns `test_voice_utterances.py` red, which is the point.
- **Label modelled values as modelled** (SC-5), everywhere they are displayed.
- **Tier is never colour alone** (NFR-07). Render it through `web/shared/tier.js`.
- Type hints on every signature, params and return, with explicit generic
  parameters. Cohesive classes for components; functions only for small stateless
  transformations.
- No leading underscores on module-level names. Fold helpers into their owning
  class as a `@staticmethod`.
- Run `uv run pre-commit run --files <changed>` before every push. Never `--no-verify`.
- Conventional commits (`feat:` `fix:` `refactor:` `test:` `docs:` `chore:`).
  Branch off `main` and open a PR — never push to `main` directly.

## Where the design lives

- [Design spec](docs/superpowers/specs/2026-07-25-climatise-scaffold-design.md) — architecture and the reasoning behind it
- [Implementation plan](docs/superpowers/plans/2026-07-25-climatise-scaffold.md) — task-by-task build
- [Architecture reference](docs/architecture.html) — the L0–L6 layer view
