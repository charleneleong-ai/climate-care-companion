# Deviations from the specification

Every departure from Climate Companion System Specification v0.1, with the reasoning.
SC-7 requires that bias toward over-warning be documented; this file is where.

---

## COLD_GUARD — cold codes only evaluate below 18 °C outdoor

**Spec:** §8.1 defines `INDOOR_BELOW_18` as `18 > indoor_day ≥ 16`, with no outdoor
condition.

**Problem.** FR-11 has no heating term. It models an *unheated* dwelling, so the
estimate tracks outdoor temperature down:

```
night 12 °C, day 19 °C, bungalow offset 0.5
  indoor_day = 0.3(12) + 0.55(19) + 0.5 + 2 = 16.55 °C
```

16.55 falls in the `INDOOR_BELOW_18` band, so §8.1 read literally raises a cold
warning on a pleasant British summer afternoon — and does it for every persona, on
most days of the year. That fails the specification's own no-cry-wolf criterion in
§13.

**Change.** All three cold codes gain the guard `peak_air < 18`, a day on which
heating is plausible at all. `HEATING_DAY_MAX` in
[`core/rules.py`](../packages/core/src/core/rules.py).

**Alternatives rejected.** Changing the FR-11 coefficients would break the §8.6
worked example, which is the system's anchor. Lowering the cold thresholds would
under-warn in genuine cold, which SC-7 forbids.

**Risk accepted.** A genuinely cold home on a mild-but-sunny day is now missed.
Judged acceptable: with outdoor peak above 18 °C the dwelling has a heat source
available for free, and the failure mode is one warning fewer in April rather than
none in January. `tests/verification/test_cold_guard.py` asserts cold codes still
fire at 2/7 °C, 8/15 °C and 14/17.5 °C.

**How it was found.** The JavaScript companion engine carried this guard before the
Python did. The Python's no-cry-wolf gate passed only because its fixture hardcoded
`indoor_day_est=21.0` — a value FR-11 does not produce for that outdoor weather. A
fixture that bypasses the model under test is not a test; `benign_season` now
derives its indoor figures from `IndoorModel`.

**Open:** FR-11 ignores `Place.heating_affordable`, which is recorded and unused. A
heated home sits near 20 °C whatever the outdoor temperature. Modelling every
dwelling as unheated is the right conservative assumption for a fuel-poor household
and the wrong one otherwise, and it should become an input rather than an accident.

---

## Multi-tenant data model built at v0.1

**Spec:** §14 puts multi-tenant management out of scope for v0.1; §15 defers an org
pilot to v1.0.

**Change.** `org_id` and `area_codes` scope every L6 query from the first commit, and
`COUNCIL`, `HOSPITAL` and `CARE_HOME` are implemented.

**Reasoning.** Retrofitting tenancy onto an existing assessment table is the
expensive mistake; declaring an unused enum value is free. No identity-provider
integration and no self-serve onboarding, so SC-6 is not crossed — every org and
cohort is fictional and seeded. `cohort_member.consent_basis` has no default, so a
person cannot be added to a cohort without stating a lawful basis.

---

## The cared-for person is a direct user

**Spec:** §1.3 defines them as "not necessarily a user of the system"; §3 lists the
caregiver as primary.

**Change.** The person receives check-ins by WhatsApp, SMS or voice, and a
prevention plan written in the second person.

**Reasoning.** NFR-05 and NFR-06 — 360 px layouts, ≥16 px text, ≥44 px targets — are
mitigations for a modality that fits an 85-year-old poorly. Messaging and voice
remove the problem rather than mitigating it, and reach people who own no
smartphone.

**Constraint.** The agent *selects* from validated text and never composes. A
generative agent would put SC-1 beyond grep on a surface that speaks unsupervised to
a vulnerable person. Enforced by `tests/verification/test_voice_utterances.py` and
`test_question_safety.py`.

---

## Resource allocation, and interaction-based advice

Neither is in the specification.

**Allocation** (`packages/allocation`) ranks a cohort on harm averted per visit
rather than risk observed, so a Severe-tier person with a live-in carer ranks below
a High-tier person living alone. Pure over its arguments, so it replays over
historical seasons.

**Interactions** (`packages/actions/interactions.py`) produce advice that exists only
in combination — heat plus a condition plus a medicine. The scoring core is
deliberately additive, which is right for a tier and wrong for advice. This is also
where FR-15 is implemented: heat-sensitive medication storage above 25 °C is a
property of neither the person nor the weather alone.

Two cases where the general advice is actively wrong, and the table says so:

- **Renal + cardiovascular.** "Drink plenty in hot weather" is dangerous for someone
  on fluid restriction for heart failure. The advice directs to the GP for a personal
  figure rather than repeating the general one.
- **Anticholinergic.** Suppressed sweating removes the *first warning sign* of
  overheating, so its absence is not reassurance. Carried as a `watch_for`, which is
  a different instruction from a `do`.

---

## Two scoring engines

`packages/core` scores in Python; `web/companion/index.html` scores in JavaScript so
the companion works with no backend, which NFR-04 requires.

Two implementations of L3 is what AC-1 and AC-5 exist to prevent, and it has already
cost once — the COLD_GUARD above existed in one engine and not the other.

`tests/verification/test_engine_parity.py` asserts every reason code, weight, tier
threshold and the fusion formula match across both. It compares *constants*, not
behaviour. **The proper fix is a shared fixture corpus both engines are run against**,
and until that exists this gate narrows the drift rather than closing it.

---

## Compounding: two rules the spec does not have

Spec 8.2 is a table of independent factors, and the vulnerability score is their
sum. That arithmetic assumes each factor acts alone. It does not.

Three long-term conditions and three heat-acting medicine classes overlap in the
systems heat already strains — fluid balance, blood pressure, and shedding heat
through the skin. The person carrying all of them is not in the same position as
someone carrying any one of them, and adding the parts up says nothing about it.

Two rules were added:

| Code | Fires when | Weight |
|---|---|---|
| `MULTIMORBIDITY` | 3 or more conditions | 2 |
| `MED_POLYPHARMACY` | 3 or more **distinct** medicine classes | 2 |

**Distinct classes, not medicine count.** Two medicines of one class are a single
mechanism dosed twice. The usual polypharmacy definition counts every medicine a
person takes; this counts only classes that already matter in heat, which is why
the threshold is 3 rather than the conventional 5 — three here is a heavier
burden than five on the usual measure.

**What it changed.** Scores rose for Doris (13 → 15), Reg (12 → 14), Victor
(14 → 18) and Winifred (13 → 15). **No persona changed tier**, on the 19 July
2025 worked-example day or anywhere in the 92-day benign season, so the
no-cry-wolf gate holds unaltered. The effect is on ranking and on what the
reader is told, not on who gets alerted.

**What it cost.** The 8.6 worked example now yields 15 rather than 13 and its
reason set gains `MED_POLYPHARMACY`, so `test_worked_example.py` no longer
reproduces the spec's literal figures. It had already stopped doing so when the
personas were enriched; this widens that gap, and the test now pins the scenario
rather than the spec's arithmetic.
