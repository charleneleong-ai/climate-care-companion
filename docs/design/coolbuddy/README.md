# CoolBuddy — mobile design handoff

Design reference for the phone surface: an AI assistant that helps a vulnerable
elderly person stay safe in extreme heat and cold. Nine screens, high fidelity —
colours, type, spacing, copy and animation timing are final-intent.

**These are references, not production code.** They are HTML/JS prototypes of the
intended look and flow. The handoff asks for them to be rebuilt in the target
codebase's own patterns rather than copied; here that means Next.js routes in
[`web/app`](../../../web/app), which is already an installable PWA.

| File | What it is |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | The brief: screens, tokens, state, interactions. Read this first. |
| [`Neighbor.dc.html`](Neighbor.dc.html) | The prototype — all nine screens, state logic, theme and avatar switching. |
| [`Avatar.dc.html`](Avatar.dc.html) | Shared avatar component: Person / Girl / Earth. |
| [`ios-frame.jsx`](ios-frame.jsx) | Device bezel for presentation only. Not product UI. |

## Viewing them

GitHub renders `.html` as source, so the prototypes are not viewable in place.

- **CoolBuddy prototype** — <https://claude.ai/code/artifact/f83b44c1-7970-4bd9-832b-e22bc7ed29ed>
- **Risk over time** — <https://claude.ai/code/artifact/bfd76cb8-fc9f-4442-9499-ad64d0107571>
  — the same three days from the engine's side: the register day by day, one
  person's trajectory, and who crosses with how much notice.

Locally, open the files directly in a browser; they are self-contained and need
no server.

## How this relates to what already runs

The prototype carries **simulated** temperatures, tiers and advice. This repo
already has the real versions of all three, and the wiring is the work:

| Prototype shows | Comes from |
|---|---|
| Condition (cold / good / hot / extreme) | `RiskScorer` — `Tier` Low / Elevated / High / Severe |
| "What do I do now" three steps | `PreventionPlanBuilder` — selected from the validated corpus, never composed |
| Risk factors ("I take a water pill") | `MedClass`, `Condition` — the copy is friendlier, the vocabulary is the core's |
| Check-in that escalates after no answer | `CheckinLog` + `EscalationPolicy` — already grades silence by history |
| Caregiver view (Dana's phone) | `Audience.CAREGIVER` — the second of the two voices every alert already carries |
| Indoor temperature | `IndoorModel` (FR-11) — modelled, and labelled as modelled wherever shown (SC-5) |

## Two decisions this raises

**Two design systems.** CoolBuddy specifies Signika + Newsreader and
condition-tinted backgrounds; the current app uses a paper/ink/teal system with
tier *shapes* rather than tier colour. They do not blend. The defensible split is
CoolBuddy for the phone (one person, their own risk) and the current system for
`/monitoring` and `/caregiver` (a register, a professional audience) — different
people on different devices.

**One rule worth keeping.** The brief fixes Home at exactly two primary actions,
forever. `/companion` currently has more. That constraint is right for the reader
it is written for, and any rebuild should inherit it rather than negotiate it.

## What the prototype cannot inherit unchanged

- **Tier colour alone.** NFR-07 requires shape and word to carry the tier too, so
  a colour-blind reader or a greyscale screen loses nothing. CoolBuddy's face
  expressions do some of this work; the tier itself still needs a word.
- **Advice text.** Every line a person reads has been through the SC-1 medication
  gate at corpus load. Prototype copy is illustrative and must be replaced by
  corpus text rather than transcribed.
- **999.** SC-3 allows it only alongside an explicit red flag, never inferred
  from a tier — so the "Call a person" list is right to include it, but the
  assistant must not volunteer it.
