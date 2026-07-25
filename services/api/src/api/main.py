from datetime import UTC, date, datetime
from typing import Any

import httpx

from contracts import AlertLevel, ExposureFeatures, ExposureSource, Place, ReasonCode
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from fastapi import FastAPI, HTTPException
from exposure.openmeteo import OpenMeteoClient
from persons.loader import PersonaLoader

app = FastAPI(
    title="Climatise Companion",
    version="0.1.0",
    description="Demonstrator. Not medical advice, and not clinically validated.",
)

CORPUS = Corpus.load()
SCORER = RiskScorer(CORPUS)
VULNERABILITY = VulnerabilityScorer()
PERSONAS = PersonaLoader()

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
        "tier": assessment.tier.name,
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
