from datetime import date
from typing import Any

from contracts import AlertLevel, ExposureFeatures, ExposureSource, ReasonCode
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from fastapi import FastAPI, HTTPException
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

# Track 0 replaces this with a live Open-Meteo client behind the same type, so
# nothing downstream notices the swap. ExposureSource already distinguishes
# FIXTURE from LIVE, which is how the provenance stays honest meanwhile.
FIXTURE_EXPOSURE = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,
    indoor_day_est=25.85,
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

    assessment = SCORER.assess(FIXTURE_EXPOSURE, VULNERABILITY.profile(person))
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
            "indoor_night_est_modelled": FIXTURE_EXPOSURE.indoor_night_est,
            "indoor_day_est_modelled": FIXTURE_EXPOSURE.indoor_day_est,
            "overnight_min": FIXTURE_EXPOSURE.overnight_min,
            "peak_apparent": FIXTURE_EXPOSURE.peak_apparent,
            "alert_level": FIXTURE_EXPOSURE.alert_level,
            "source": FIXTURE_EXPOSURE.source,
        },
        "not_medical_advice": True,  # SC-2
    }
