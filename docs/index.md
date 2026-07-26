---
title: Climate Care Companion
---

# Climate Care Companion

A heat-health risk service that answers a question a weather forecast cannot:
**is tonight dangerous for _this_ person?** Two people on the same street can
face very different nights — it depends on age, conditions, medicines, and how
hot the bedroom actually gets.

> **Demonstrator only.** Not medical advice and not clinically validated. Every
> person in these documents is fictional.

## Try it

**[Live demo](https://starsmerchant-away-mouse-armed.trycloudflare.com/)** —
`/companion` for one person's view, `/monitoring` for the register.

> A Cloudflare quick tunnel to a laptop. **The address changes every time the
> tunnel restarts.** If it does not load it has expired rather than broken; the
> repo below runs the same thing locally.

## Design

- [CoolBuddy — mobile handoff](design/coolbuddy/) — the phone surface: nine
  screens, tokens, avatar variants, animation timings
  - [Open the prototype](design/coolbuddy/Neighbor.dc.html) · [avatar component](design/coolbuddy/Avatar.dc.html)
  - [The brief](design/coolbuddy/HANDOFF.md)

## Architecture

- [Architecture](architecture.md) — how the layers talk to each other
- [Architecture reference](architecture-reference.html) — the diagrams
- [Reconciliation](reconciliation.md) — why there is one risk engine and not
  three, and what it cost to get there
- [Deviations](deviations.md) — where the build departs from the brief, and why

## The argument, in one view

[Risk over the days](https://claude.ai/code/artifact/bfd76cb8-fc9f-4442-9499-ad64d0107571)
— the register across 17–19 July 2025. No regional alert was issued on any of
those three days. Per-person assessment finds twelve people at risk with two
days of notice.

## Source

[github.com/charleneleong-ai/climate-care-companion](https://github.com/charleneleong-ai/climate-care-companion)

| Package | What it does |
|---|---|
| `packages/core` | Declarative exposure and vulnerability rules. Pure — no I/O, no clock. |
| `packages/exposure` | FR-11 indoor model. Same weather, 2.3°C between a top-floor south flat and a ground-floor north bungalow. |
| `packages/actions` | Prevention plans, and the escalation ladder for when advice stops being enough. |
| `packages/checkin` | The questionnaire, the channels, and what was actually said. |
| `services/scheduler` | The three-hourly sweep — the only part that initiates. |
| `services/voice` | The check-in as a phone call. |
