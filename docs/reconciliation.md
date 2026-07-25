# Reconciling the two risk models

There are now two independent implementations of "how dangerous is this weather
for this person", built from the same brief and arriving at genuinely different
answers. This records what each does, where each is better, and what was done
about it.

Neither is a bad version of the other. They disagree about the *shape* of the
problem.

| | `web/app` — TypeScript | `packages/core` — Python |
|---|---|---|
| Output | 7 bands, severity 0–100, continuous | 4 tiers, risk score, discrete |
| Mechanism | shifts the person's **thresholds** inward | multiplies **exposure** by a vulnerability factor |
| Temperature used | outdoor apparent (feels-like) | modelled **indoor** (FR-11) |
| Cold | full symmetric parity with heat | heat-primary, cold behind a guard |
| Medication | one checkbox | seven pharmacological classes, weighted |
| Combinations | none | 18 interaction rules |
| Data | **live** Open-Meteo + postcodes.io | fixtures |
| Compounding | diminishing returns, saturating | linear, unbounded |
| UX affordances | headroom to next band, worsening-today | none |

---

## Where the TypeScript model is better

**Threshold-shifting is closer to the brief's own definition.** §1.3 defines
extreme temperature as "any condition beyond what a specific body can regulate
against. A personal threshold, not an absolute one." That is literally what
`personalThresholds` computes. The Python implements the brief's *algorithm* (§8)
faithfully while being further from the brief's *definition*.

**Compounding saturates.** `compound()` takes the largest factor at full weight
and half of each remaining one, then `soften()` maps it onto a curve that never
reaches the cap. The Python's `1 + vulnerability/10` is linear and unbounded: a
person ticking every box gets a multiplier of 2.6 and nothing stops it climbing.
The comment in `risk.ts` records that summing "drove the comfortable band shut" —
the Python has the same failure mode and has not hit it only because its
vulnerability weights happen to be small.

**Cold is a first-class direction**, not an afterthought behind `COLD_GUARD`. It
also does not have the Python's cry-wolf bug, because it bands on outdoor apparent
temperature rather than a modelled indoor figure that dips below 18 °C on a
pleasant afternoon.

**`assertOrdered` is a guard the Python lacks** — it fails loudly if thresholds
stop being strictly increasing rather than silently misclassifying.

**Headroom and worsening-today.** "1.8 °C until this gets worse" and "today's
forecast crosses a worse band than right now" are exactly the affordances a
prevention plan needs, and the Python produces neither.

**It has live data.** Open-Meteo and postcodes.io are wired and working; the
Python still serves fixtures.

## Where the Python model is better

**Medication granularity, and this one matters most.** The TypeScript profile
carries a single `medication` factor worth 2 °C on the heat side. The Python
scores seven classes separately:

```
lithium 3   diuretic 2   anticholinergic 2   antipsychotic 2
ace_arb 1   beta_blocker 1   ssri 1
```

Lithium is the heaviest single vulnerability weight in the whole specification,
because dehydration concentrates it and the safe range is narrow. A checkbox
cannot distinguish that from being on a beta blocker. The architecture reference
calls medication "the differentiator"; collapsing it to one flag removes the
differentiator.

**Indoor modelling.** §12.2 names modelled indoor temperature as the dominant
error term, and `BEDROOM_UNSAFE` carries weight 3. The TypeScript model has no
indoor concept at all, so a top-floor flat and a ground-floor bungalow under the
same sky are identical to it. `dwelling_offset` exists in the Python for exactly
this and now runs live.

**Interactions.** FR-15 (insulin above 25 °C), renal + cardiovascular (where
"drink plenty" is actively dangerous), anticholinergic (where suppressed sweating
removes the first warning sign). None of this is expressible as a sum of factors.

**Enforced safety.** SC-1 is greppable and checked at load; SC-3 red flags have
declared polarity; the §8.6 worked example and no-cry-wolf run in CI.

---

## What was done

The TypeScript app is the front end, so it keeps its own scoring — it must work
offline and without the Python running. What it should not do is carry its own
*clinical content*, which is where the Python is stronger and where being wrong
matters most.

`core.export` now emits, alongside the rules and parity corpus:

- `med_class_weights` — the seven classes and their weights
- `interactions` — all 18 rules with both audience voices, watch-for text,
  escalation target and supersedes list

`tests/verification/test_generated_freshness.py` fails the build if these drift
from the Python.

## What has not been done, and should be

**The TypeScript app does not yet read the generated file.** It is exported and
gated; consuming it is the next step. Until then this document describes an
available bridge, not a closed loop.

**The medication checkbox is still one checkbox.** Replacing it with a class
picker is a UI change in `onboarding/page.tsx` plus a `Profile.factors` widening.
Until that lands the front end cannot tell lithium from a beta blocker, and that
is the single largest clinical gap between the two models.

**No indoor modelling in the front end.** `overheatingHome` and `coldHome` are
coarse proxies for `dwelling_offset`. The offset lookup is exportable.

**The two models have never been run against the same inputs.** The parity corpus
pins Python's answers for seven boundary cases; nothing yet checks what the
TypeScript returns for them. That comparison is the honest test of whether these
can be reconciled at all, or whether one has to give way.

**Unresolved: which model wins.** Threshold-shifting and score-multiplying cannot
both be the answer. My recommendation is that the *thresholds* approach is the
better spine — it matches the brief's definition and it saturates — and that the
Python's medication classes, indoor model and interaction rules should be ported
onto it rather than the reverse. That is a bigger change than a hackathon
weekend, and it needs a decision before either model is presented as the one the
project stands behind.
