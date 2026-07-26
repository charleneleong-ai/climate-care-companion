from datetime import UTC, date, datetime
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
from exposure.openmeteo import OpenMeteoClient
from persons.loader import PersonaLoader

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

WEATHER = OpenMeteoClient(httpx.Client())
"""Live. NFR-03 gives it three seconds, NFR-04 falls back to the last snapshot,
and ExposureSource says which happened — so a stale figure is never presented as
a fresh one."""

# Where the person is, until postcodes.io geocoding lands. Bedford, because that
# is the section 8.6 worked example and the highest heat-mortality rate in
# England last summer.
FALLBACK_LAT, FALLBACK_LON = 52.1364, -0.4669


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
def get_assessment(person_id: str) -> dict[str, Any]:
    """Read path. Serves a computed assessment — no network call on this request."""
    person = PERSONAS.load().get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"no person with id {person_id!r}")

    place = PERSONAS.places()[person_id]
    try:
        exposure = exposure_for(place, date.today())
    except LookupError as exc:
        # No live forecast and nothing cached. Inventing one would be worse than
        # saying so — a caregiver acting on a fabricated figure is the failure
        # this whole system exists to prevent.
        raise HTTPException(
            status_code=503,
            detail="No forecast available and no cached assessment to fall back on.",
        ) from exc
    assessment = SCORER.assess(exposure, VULNERABILITY.profile(person))
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
    lat: float = FALLBACK_LAT
    lon: float = FALLBACK_LON
    dwelling_type: DwellingType = DwellingType.HOUSE
    floor: int = 0
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
            aspect=Aspect.SOUTH,
            has_cooling=self.has_cooling,
            heating_affordable=True,
            dwelling_offset=offset,
        )


class AssessRequest(BaseModel):
    person: PersonRequest
    place: PlaceRequest = Field(default_factory=PlaceRequest)
    dwelling_offset: float = 1.2
    """Until the front end collects dwelling detail, a middling home. The offset
    is the input FR-11 actually needs, so it is accepted directly rather than
    guessed from a coldHome/overheatingHome checkbox."""
    audience: Audience = Audience.CAREGIVER


@app.post("/assess")
def assess(request: AssessRequest) -> dict[str, Any]:
    """Assess anyone, not only a seeded persona.

    This is the endpoint the front end calls now that it no longer scores. It
    returns the assessment and the prevention plan together, because a tier
    without a next step is a weather app.
    """
    person = request.person.to_person()
    place = request.place.to_place(person.id, request.dwelling_offset)

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
