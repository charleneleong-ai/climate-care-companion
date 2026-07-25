from datetime import date
from typing import Any

from contracts import AlertLevel, ExposureFeatures, ExposureSource, Place, ReasonCode
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from fastapi import FastAPI, HTTPException
from exposure.indoor import IndoorModel
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

INDOOR = IndoorModel()

# Outdoor weather is still fixed — Track 0 replaces this with a live Open-Meteo
# client behind the same type, and ExposureSource keeps the provenance honest
# meanwhile. The indoor figures are no longer fixed: they are computed per person
# from their own dwelling, which is the whole point of recording it.
OUTDOOR_NIGHT_MIN = 17.0
OUTDOOR_DAY_MAX = 29.0


def exposure_for(place: Place) -> ExposureFeatures:
    """FR-11 applied to this person's dwelling.

    A top-floor south-facing flat and a ground-floor north-facing bungalow see the
    same weather and a different bedroom, which is the difference the offset exists
    to carry.
    """
    return ExposureFeatures(
        date=date(2025, 7, 19),
        overnight_min=OUTDOOR_NIGHT_MIN,
        peak_apparent=OUTDOOR_DAY_MAX,
        peak_air=OUTDOOR_DAY_MAX,
        hours_above_26=7,
        indoor_night_est=INDOOR.night(
            OUTDOOR_NIGHT_MIN, OUTDOOR_DAY_MAX, place.dwelling_offset
        ),
        indoor_day_est=INDOOR.day(
            OUTDOOR_NIGHT_MIN, OUTDOOR_DAY_MAX, place.dwelling_offset
        ),
        spell_day=3,
        alert_level=AlertLevel.NOT_CHECKED,
        source=ExposureSource.FIXTURE,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "personas": len(PERSONAS.load()),
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
    exposure = exposure_for(place)
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
