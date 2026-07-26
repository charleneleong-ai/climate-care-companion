from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from contracts import (
    AgeBand,
    Aspect,
    AlertLevel,
    Audience,
    Condition,
    DwellingType,
    ExposureFeatures,
    ExposureSource,
    Med,
    MedClass,
    Person,
    Place,
    ReasonCode,
    Tier,
)
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from actions.checklist import PreventionPlanBuilder
from actions.interactions import InteractionTable
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from checkin.env import load_env
from checkin.webpush import PushPayload, PushSubscription, SubscriptionStore, WebPushChannel
from exposure.indoor import IndoorModel
from exposure.openmeteo import OpenMeteoClient
from persons.loader import PersonaLoader, floor_band, load_dwelling_offsets

load_env()

app = FastAPI(
    title="Climatise Companion",
    version="0.1.0",
    description="Demonstrator. Not medical advice, and not clinically validated.",
)

CORPUS = Corpus.load()
SCORER = RiskScorer(CORPUS)
VULNERABILITY = VulnerabilityScorer()
PERSONAS = PersonaLoader()
PLANNER = PreventionPlanBuilder(CORPUS, InteractionTable.load())

INDOOR = IndoorModel()

WEATHER = OpenMeteoClient(httpx.Client())
"""Live. NFR-03 gives it three seconds, NFR-04 falls back to the last snapshot,
and ExposureSource says which happened — so a stale figure is never presented as
a fresh one."""

# Where the person is, until postcodes.io geocoding lands. Bedford, because that
# is the section 8.6 worked example and the highest heat-mortality rate in
# England last summer.
FALLBACK_LAT, FALLBACK_LON = 52.1364, -0.4669

FORECAST_HORIZON = 7
"""Days to attempt. Open-Meteo currently returns three; asking for more costs
nothing and means the view lengthens by itself when the horizon does, rather
than silently staying short."""


def exposure_for(place: Place, day: date) -> ExposureFeatures:
    """Live forecast, then FR-07 to FR-11 applied to this person's dwelling.

    A top-floor south-facing flat and a ground-floor north-facing bungalow see the
    same weather and a different bedroom, which is the difference the offset
    exists to carry.
    """
    latitude = place.lat or FALLBACK_LAT
    longitude = place.lon or FALLBACK_LON
    forecast = WEATHER.fetch(latitude, longitude, datetime.now(UTC))
    return WEATHER.features_for(forecast, day, place.dwelling_offset)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "personas": len(PERSONAS.load()),
        "weather": "live (Open-Meteo)",
        "reason_codes": len(ReasonCode),
        "reasons_loaded": len(CORPUS.reasons),
        "actions_loaded": len(CORPUS.actions),
    }


@app.get("/people")
def list_people() -> list[dict[str, Any]]:
    return [
        {"id": person.id, "name": person.name, "age_band": person.age_band}
        for person in PERSONAS.load().values()
    ]


@app.get("/people/{person_id}/assessment")
def get_assessment(
    person_id: str,
    audience: Audience = Audience.CAREGIVER,
    fixture: str | None = None,
) -> dict[str, Any]:
    """A seeded persona's assessment and their plan.

    Returns the plan as well as the tier, matching `/assess`, so signing in as a
    persona lands on the same screen a real sign-up does. A tier without a next
    step is a weather app.
    """
    person = PERSONAS.load().get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"no person with id {person_id!r}")

    place = PERSONAS.places()[person_id]
    if fixture == "heat":
        exposure = heat_fixture_for(place.dwelling_offset)
    else:
        try:
            exposure = exposure_for(place, date.today())
        except LookupError as exc:
            # No live forecast and nothing cached. Inventing one would be worse
            # than saying so — a caregiver acting on a fabricated figure is the
            # failure this whole system exists to prevent.
            raise HTTPException(
                status_code=503,
                detail="No forecast available and no cached assessment to fall back on.",
            ) from exc
    assessment = SCORER.assess(exposure, VULNERABILITY.profile(person))
    plan = PLANNER.build(person, exposure, assessment, audience)
    return {
        "person_id": person.id,
        "name": person.name,
        "tier": assessment.tier.name.title(),
        "risk_score": assessment.risk_score,
        "exposure_score": assessment.exposure_score,
        "vulnerability_score": assessment.vulnerability_score,
        "reasons": [
            {
                "code": reason.code,
                "title": reason.title,
                "explanation": reason.explanation,
                "weight": reason.weight,
            }
            for reason in assessment.reasons
        ],
        "exposure": {
            # SC-5: the key name carries the label, so no caller can drop it on the
            # way to a screen.
            "indoor_night_est_modelled": round(exposure.indoor_night_est, 2),
            "indoor_day_est_modelled": round(exposure.indoor_day_est, 2),
            "overnight_min": exposure.overnight_min,
            "peak_apparent": exposure.peak_apparent,
            "dwelling_offset": place.dwelling_offset,
            "alert_level": exposure.alert_level,
            "source": exposure.source,
        },
        "plan": {
            "audience": plan.audience,
            "items": [
                {
                    "code": item.code,
                    "text": item.text,
                    "watch_for": item.watch_for,
                    "escalate_to": item.escalate_to,
                    "source": item.source,
                }
                for item in plan.items
            ],
            "watch_points": list(plan.watch_points),
            "escalate_to": list(plan.escalation_targets()),
        },
        "not_medical_advice": True,  # SC-2
    }


class PersonRequest(BaseModel):
    """A person in the core's vocabulary, not the front end's.

    The front end translates on the way out, using the one table in codes.ts
    that already holds every disagreement between the two spellings. Accepting
    the app's vocabulary here would put that mapping in two places, which is the
    drift this convergence exists to end.
    """

    id: str = "adhoc"
    name: str = "Someone"
    age_band: AgeBand
    lives_alone: bool = False
    mobility_limited: bool = False
    conditions: list[Condition] = Field(default_factory=list)
    med_classes: list[MedClass] = Field(default_factory=list)

    def to_person(self) -> Person:
        return Person(
            id=self.id,
            name=self.name,
            age_band=self.age_band,
            lives_alone=self.lives_alone,
            mobility_limited=self.mobility_limited,
            conditions=tuple(self.conditions),
            medications=tuple(Med(m.value, m) for m in self.med_classes),
        )


class PlaceRequest(BaseModel):
    """Where the person sleeps, in enough detail to model the bedroom.

    `aspect` is asked for rather than assumed south. FR-11's offsets span 2.8°C
    between a top-floor south-facing flat and a ground-floor north-facing one —
    larger than the gap between tiers — so guessing it does not produce a slightly
    wrong answer, it produces a different one.
    """

    lat: float = FALLBACK_LAT
    lon: float = FALLBACK_LON
    dwelling_type: DwellingType = DwellingType.HOUSE
    floor: int = 0
    aspect: Aspect = Aspect.SOUTH
    has_cooling: bool = False

    def to_place(self, person_id: str, offset: float) -> Place:
        return Place(
            person_id=person_id,
            postcode="",
            lat=self.lat,
            lon=self.lon,
            admin_district="",
            region="",
            dwelling_type=self.dwelling_type,
            floor=self.floor,
            aspect=self.aspect,
            has_cooling=self.has_cooling,
            heating_affordable=True,
            dwelling_offset=offset,
        )


# Spec §8.6 worked example — Bedford, 19 July 2025. No regional heat-health
# alert was issued that day, which is the entire point of the fixture: HIGH tier
# with alert_level=NONE. Used by ?fixture=heat for the demo, and by the
# verification suite. Hardcoded so the demo is repeatable whatever today's
# weather happens to be.
HEAT_FIXTURE = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,
    indoor_day_est=25.85,
    spell_day=3,
    alert_level=AlertLevel.NONE,
    source=ExposureSource.FIXTURE,
)


def heat_fixture_for(dwelling_offset: float) -> ExposureFeatures:
    """The worked example as one particular building would experience it.

    The fixture's own estimates are for a 2.8°C offset. A bungalow does not get
    a top-floor flat's bedroom, so the two indoor figures are re-derived through
    FR-11 while everything outdoors stays fixed.

    Shared because both fixture routes had grown their own arithmetic and drifted
    apart: /assess put Doris at 24.6°C and High, the persona route at 19.8°C and
    Elevated — the same woman on the same day, two different answers depending on
    which screen you opened. Neither touched indoor_day_est at all, so every
    persona was served the fixture's 25.85 whatever their home.
    """
    return replace(
        HEAT_FIXTURE,
        indoor_night_est=INDOOR.night(
            HEAT_FIXTURE.overnight_min, HEAT_FIXTURE.peak_air, dwelling_offset
        ),
        indoor_day_est=INDOOR.day(
            HEAT_FIXTURE.overnight_min, HEAT_FIXTURE.peak_air, dwelling_offset
        ),
    )


# Episode 4 as it actually built: 17 to 19 July 2025, England, ~146 excess deaths
# and no regional alert on any of the three days. The 19th is HEAT_FIXTURE above;
# the two days before it are what a council would have been able to see coming.
#
# The point of holding all three rather than only the peak is that the argument
# is about lead time. On the 17th the register is mostly quiet; by the 19th it is
# not, and every hour in between was available to act in.
HEAT_EPISODE = (
    replace(
        HEAT_FIXTURE,
        date=date(2025, 7, 17),
        overnight_min=14.0,
        peak_apparent=26.0,
        peak_air=26.0,
        hours_above_26=2,
        indoor_night_est=21.0,
        indoor_day_est=22.8,
        spell_day=1,
    ),
    replace(
        HEAT_FIXTURE,
        date=date(2025, 7, 18),
        overnight_min=15.5,
        peak_apparent=27.5,
        peak_air=27.5,
        hours_above_26=5,
        indoor_night_est=22.9,
        indoor_day_est=24.3,
        spell_day=2,
    ),
    HEAT_FIXTURE,
)


class AssessRequest(BaseModel):
    person: PersonRequest
    place: PlaceRequest = Field(default_factory=PlaceRequest)
    dwelling_offset: float | None = None
    """Override for a caller that already holds a measured offset. Left unset,
    the offset is looked up from the same FR-11 table the personas use — so a
    web sign-up and a seeded persona are modelled by one rule rather than two.

    It used to default to 1.2, "a middling home". That silently invented the
    single input the indoor model is most sensitive to, and reported the result
    with the same confidence as a real one.
    """
    audience: Audience = Audience.CAREGIVER
    fixture: str | None = None
    """Pass 'heat' to substitute the Bedford 19 July 2025 fixture instead of
    fetching live weather. Intended for demos and for verifying the full stack
    against a known scenario on any day of the year.
    Other values are rejected with 422 so a typo never silently produces a
    fabricated assessment.
    """

    def offset(self) -> float:
        if self.dwelling_offset is not None:
            return self.dwelling_offset
        key = (
            self.place.dwelling_type.value,
            floor_band(self.place.floor),
            self.place.aspect.value,
        )
        offsets = load_dwelling_offsets()
        if key not in offsets:
            raise HTTPException(422, f"no dwelling offset for {key}")
        return offsets[key]


@app.post("/assess")
def assess(request: AssessRequest) -> dict[str, Any]:
    """Assess anyone, not only a seeded persona.

    This is the endpoint the front end calls now that it no longer scores. It
    returns the assessment and the prevention plan together, because a tier
    without a next step is a weather app.

    Pass fixture='heat' in the body to use the Bedford 19 July 2025 scenario
    instead of live weather — useful for demos and integration tests.
    """
    if request.fixture is not None and request.fixture != "heat":
        raise HTTPException(
            status_code=422,
            detail=f"Unknown fixture {request.fixture!r}. Only 'heat' is supported.",
        )

    person = request.person.to_person()
    place = request.place.to_place(person.id, request.offset())

    if request.fixture == "heat":
        exposure = heat_fixture_for(place.dwelling_offset)
    else:
        try:
            exposure = exposure_for(place, date.today())
        except LookupError as exc:
            raise HTTPException(
                status_code=503,
                detail="No forecast available and nothing cached to fall back on.",
            ) from exc

    assessment = SCORER.assess(exposure, VULNERABILITY.profile(person))
    plan = PLANNER.build(person, exposure, assessment, request.audience)

    return {
        "person_id": person.id,
        "tier": assessment.tier.name.title(),
        "risk_score": assessment.risk_score,
        "exposure_score": assessment.exposure_score,
        "vulnerability_score": assessment.vulnerability_score,
        "reasons": [
            {"code": r.code, "title": r.title, "explanation": r.explanation, "weight": r.weight}
            for r in assessment.reasons
        ],
        "exposure": {
            "indoor_night_est_modelled": round(exposure.indoor_night_est, 2),
            "indoor_day_est_modelled": round(exposure.indoor_day_est, 2),
            "overnight_min": exposure.overnight_min,
            "peak_apparent": exposure.peak_apparent,
            "peak_air": exposure.peak_air,
            "spell_day": exposure.spell_day,
            "dwelling_offset": place.dwelling_offset,
            "alert_level": exposure.alert_level,
            "source": exposure.source,
        },
        "plan": {
            "audience": plan.audience,
            "items": [
                {
                    "code": i.code,
                    "text": i.text,
                    "watch_for": i.watch_for,
                    "escalate_to": i.escalate_to,
                    "source": i.source,
                }
                for i in plan.items
            ],
            "watch_points": list(plan.watch_points),
            "escalate_to": list(plan.escalation_targets()),
        },
        "not_medical_advice": True,
    }


# ── Push registration ────────────────────────────────────────────────────────
#
# Held here rather than in the Next.js process because the three-hourly sweep
# reads the same store, and a copy in the web tier would be the wrong one within
# a restart.

SUBSCRIPTIONS = SubscriptionStore()


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    person_id: str
    audience: Audience


class UnsubscribeRequest(BaseModel):
    endpoint: str


@app.post("/push/subscribe")
def push_subscribe(request: SubscribeRequest) -> dict[str, Any]:
    if request.person_id not in PERSONAS.load():
        raise HTTPException(404, f"no person {request.person_id}")
    SUBSCRIPTIONS.add(
        PushSubscription(
            endpoint=request.endpoint,
            p256dh=request.p256dh,
            auth=request.auth,
            person_id=request.person_id,
            audience=request.audience,
        )
    )
    return {"registered": True, "devices": len(SUBSCRIPTIONS.subscriptions)}


@app.delete("/push/subscribe")
def push_unsubscribe(request: UnsubscribeRequest) -> dict[str, Any]:
    SUBSCRIPTIONS.remove(request.endpoint)
    return {"registered": False, "devices": len(SUBSCRIPTIONS.subscriptions)}


@app.post("/push/test/{person_id}")
def push_test(person_id: str, audience: Audience = Audience.CAREGIVER) -> dict[str, Any]:
    """Fire one real notification, so a demo can prove the phone buzzes.

    Deliberately marked as a test in the body. A notification indistinguishable
    from a real alert is a false positive with a person's name on it.
    """
    channel = WebPushChannel(store=SUBSCRIPTIONS)
    outcomes = channel.send_to(
        person_id,
        audience,
        PushPayload(
            title="Climatise — test alert",
            body="This is a test. Your alerts are working.",
            tier=Tier.ELEVATED,
            person_id=person_id,
        ),
    )
    # Per-device, because "it failed" is not actionable when three phones are
    # registered and only one is broken.
    return {
        "devices": len(outcomes),
        "delivered": sum(1 for o in outcomes if o.delivered),
        "results": [
            {
                "endpoint": o.endpoint[:60],
                "status": o.status,
                "error": o.error,
                "removed": o.should_prune,
            }
            for o in outcomes
        ],
    }


# ── Monitoring over the forecast horizon ─────────────────────────────────────


@app.get("/monitoring/forecast")
def monitoring_forecast(scenario: str | None = None) -> dict[str, Any]:
    """The whole register scored against every day the forecast covers.

    The static monitoring view argues from one day in the past. This is the same
    argument made prospectively: who on the register crosses into risk, and how
    much warning there is before they do.

    Lead time is the point. A person who is Low today and High on Wednesday can
    still be helped on Tuesday — moving tablets off a windowsill, settling a
    fluid plan with the pharmacist. The same information on Wednesday evening is
    a report rather than a prevention.
    """
    people = PERSONAS.load()
    places = PERSONAS.places()
    heat = scenario == "heat"
    today = HEAT_EPISODE[0].date if heat else date.today()
    horizon = len(HEAT_EPISODE) if heat else FORECAST_HORIZON

    days: list[dict[str, Any]] = []
    first_risk: dict[str, str] = {}

    for offset in range(horizon):
        day = today + timedelta(days=offset)
        counts: dict[str, int] = {tier.name.title(): 0 for tier in Tier}
        unavailable = 0
        peak: float | None = None

        for person_id, person in people.items():
            try:
                exposure = (
                    episode_exposure(offset, places[person_id])
                    if heat
                    else exposure_for(places[person_id], day)
                )
            except (LookupError, KeyError):
                # Beyond the horizon, or no forecast for that place. Counted
                # rather than dropped — a day we cannot see is not a safe day.
                unavailable += 1
                continue
            assessment = SCORER.assess(exposure, VULNERABILITY.profile(person))
            counts[assessment.tier.name.title()] += 1
            peak = exposure.peak_air if peak is None else max(peak, exposure.peak_air)
            if assessment.tier > Tier.LOW and person_id not in first_risk:
                first_risk[person_id] = day.isoformat()

        if unavailable == len(people):
            break

        days.append(
            {
                "date": day.isoformat(),
                "lead_days": offset,
                "peak_air": peak,
                "tiers": counts,
                "at_risk": sum(n for tier, n in counts.items() if tier != "Low"),
                "unavailable": unavailable,
            }
        )

    return {
        "register_size": len(people),
        "scenario": "heat" if heat else "live",
        "label": ("17–19 July 2025 · England · no alert issued" if heat else "Live forecast"),
        "days": days,
        # Who to act on first, and how long there is to do it.
        "first_at_risk": [
            {
                "person_id": pid,
                "name": people[pid].name,
                "date": when,
                "lead_days": (date.fromisoformat(when) - today).days,
            }
            for pid, when in sorted(first_risk.items(), key=lambda kv: kv[1])
        ],
    }


def episode_exposure(offset: int, place: Place) -> ExposureFeatures:
    """One day of Episode 4, with the bedroom modelled for this person's home.

    The fixture holds the outdoor day; the indoor estimate has to come from
    `IndoorModel` rather than a formula written here. Substituting an
    approximation would give every person on the register a bedroom the scoring
    core never predicted, and quietly break the worked example the verification
    suite pins — a fixture that bypasses the model under test is not a fixture.
    """
    day = HEAT_EPISODE[offset]
    return replace(
        day,
        indoor_night_est=INDOOR.night(day.overnight_min, day.peak_air, place.dwelling_offset),
        indoor_day_est=INDOOR.day(day.overnight_min, day.peak_air, place.dwelling_offset),
    )


@app.get("/people/{person_id}/series")
def person_series(person_id: str, scenario: str | None = None) -> dict[str, Any]:
    """One person's tier across the days, rather than tonight alone.

    The companion screen answers "is it safe tonight?". That is the right first
    question, but it hides the shape: someone Low today and High on Saturday
    needs to hear it on Thursday, and a caregiver who only ever sees tonight
    cannot plan a weekend around it.
    """
    person = PERSONAS.load().get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"no person with id {person_id!r}")

    place = PERSONAS.places()[person_id]
    heat = scenario == "heat"
    start = HEAT_EPISODE[0].date if heat else date.today()
    horizon = len(HEAT_EPISODE) if heat else FORECAST_HORIZON

    points: list[dict[str, Any]] = []
    for offset in range(horizon):
        day = start + timedelta(days=offset)
        try:
            exposure = episode_exposure(offset, place) if heat else exposure_for(place, day)
        except (LookupError, KeyError):
            break
        assessment = SCORER.assess(exposure, VULNERABILITY.profile(person))
        points.append(
            {
                "date": day.isoformat(),
                "tier": assessment.tier.name.title(),
                "risk_score": assessment.risk_score,
                "peak_air": exposure.peak_air,
                # SC-5 travels with the number, not in a caption somewhere else.
                "indoor_night_est_modelled": round(exposure.indoor_night_est, 1),
            }
        )

    return {
        "person_id": person_id,
        "name": person.name,
        "scenario": "heat" if heat else "live",
        "points": points,
    }
