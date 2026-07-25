# Climatise — Climate Care Companion

Determines whether current or forecast weather constitutes a health risk **to a
specific individual**, and tells their caregiver what to do about it.

Not a weather application. A personal risk assessment service that consumes weather
as one of several inputs.

> **Demonstrator only.** The medication rules have not been reviewed by a registered
> pharmacist (SC-4) and the weighting scheme is expert judgement, not empirically
> fitted. Not medical advice. Personas are fictional; no real health data is stored
> (SC-6).

## Why it exists

On 17–19 July 2025 no heat-health alert was issued in any English region. An
estimated 146 people died, with statistically significant mortality in care homes
and the 85-and-over group.

The national alerting cascade runs UKHSA → NHS England → integrated care boards →
providers. Every link joins one organisation to another. There is no final link from
organisation to individual, and the 5.8 million unpaid carers in the UK are not in
the cascade at any point — no register of them exists.

The scaffold's headline test asserts exactly this case: Doris, 88, in Bedford on
19 July 2025 returns **HIGH** with no regional alert in force.

```bash
uv run pytest tests/verification/test_worked_example.py -v
```

## The chain

```
predict the heatwave  →  assess the individual  →  allocate scarce capacity  →  act
    (lead time)             (tier + reasons)          (preparation)            (response)
```

## Quick start

```bash
uv sync --all-packages
uv run pytest                                    # full suite
uv run uvicorn api.main:app --reload             # http://localhost:8000/docs
python3 -m http.server 8080 --directory web      # the four web surfaces
```

Then: [companion](http://localhost:8080/companion/) ·
[national view](http://localhost:8080/national/) ·
[geographic explorer](http://localhost:8080/explorer/)

## What is green, what is not

| Layer | State |
|---|---|
| `contracts` — types crossing every boundary | green, frozen |
| `core` — L2 vulnerability, L3 risk fusion | green |
| `exposure` — FR-11 indoor model, normalisation | green (fixture-backed sources) |
| `persons` / `geography` — schema-validated data loaders | green |
| `predictors` — deterministic heatwave baseline | green; ensemble model unclaimed |
| `checkin` — closed-utterance voice scripting | green; telephony unclaimed |
| `allocation` — ranking, coverage gap, siting delta | green |
| `actions` — checklist, notification policy | **stub, Track A** |
| `org` — council / hospital / care-home views | models green, views **stub, Track B** |

Stubs raise `NotImplementedError` naming their owning track. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## The four merge gates

In `tests/verification/`. These must never go red.

| Gate | Asserts |
|---|---|
| `test_worked_example.py` | Spec §8.6 reproduces exactly — risk 6.0, tier HIGH, exact reason set |
| `test_no_cry_wolf.py` | No persona alarms on any of 92 benign days |
| `test_safety_corpus.py` | No medication action advises altering a prescription (SC-1) |
| `test_voice_utterances.py` | Every utterance the voice agent can speak is a corpus row |

## Design decisions worth knowing

**L3 is deterministic and takes no I/O.** `RiskScorer.assess()` has no database, no
clock, no network. Historical replay and the offline demo fall out of the signature
rather than needing a mode flag.

**Vulnerability multiplies exposure, it does not add to it.** Zero exposure returns
Low however frail the person, which is what stops a frail person sitting permanently
at Elevated and destroying the signal.

**Allocation ranks on harm averted, not risk observed.** A Severe-tier person with a
live-in carer ranks below a High-tier person living alone, because someone is
already watching the first one.

**The voice agent selects utterances, it never composes them.** That is what keeps
SC-1 greppable on a surface that speaks unsupervised to a vulnerable person.

**Indoor temperature is the dominant error term** at ±3–5 °C. A bedroom sensor fixes
it in v0.3; asking "is your bedroom uncomfortably warm?" on a check-in closes part of
the gap today.

## Attribution

Weather data from [Open-Meteo](https://open-meteo.com) under CC BY 4.0. Alert levels,
episode dates and mortality figures from UKHSA *Heat mortality monitoring report,
England: 2025* and *Cold mortality monitoring report, winter 2024 to 2025* — Crown
copyright, Open Government Licence v3.0.
