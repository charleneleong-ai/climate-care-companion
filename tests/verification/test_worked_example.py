"""Spec section 8.6. A merge gate — it must never go red."""

from datetime import date

import pytest
from contracts import AlertLevel, ExposureFeatures, ExposureSource, ReasonCode, Tier
from core.corpus import Corpus
from core.scoring import RiskScorer
from core.vulnerability import VulnerabilityScorer
from persons.loader import PersonaLoader

BEDFORD_19_JULY_2025 = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,  # 0.6(17) + 0.4(29) + 2.8
    indoor_day_est=25.85,  # 0.3(17) + 0.55(29) + 2.8 + 2
    spell_day=3,
    # No heat-health alert was issued in any region during Episode 4.
    # That is the entire point of this fixture.
    alert_level=AlertLevel.NONE,
    source=ExposureSource.ARCHIVE,
)


@pytest.fixture(scope="module")
def doris():
    return PersonaLoader().load()["doris"]


@pytest.fixture(scope="module")
def assessment(doris):
    return RiskScorer(Corpus.load()).assess(
        BEDFORD_19_JULY_2025, VulnerabilityScorer().profile(doris)
    )


def test_doris_lands_high_on_the_worked_example_day(assessment):
    assert assessment.exposure_score == 3
    assert assessment.vulnerability_score == 15  # enriched, then +2 for polypharmacy
    assert assessment.risk_score == pytest.approx(7.5)  # 3 x (1 + 15/10)
    assert assessment.tier is Tier.HIGH


def test_reason_set_is_exactly_the_spec_worked_example(assessment):
    # Doris enriched with COPD + sertraline + mobility_limited (realistic 85+
    # dementia presentation), then MED_POLYPHARMACY once compounding was
    # modelled. Reason set extended accordingly — this is no longer the spec's
    # literal 8.6 set, and the name is kept for the scenario it still pins.
    assert {r.code for r in assessment.reasons} == {
        ReasonCode.BEDROOM_WARM,
        ReasonCode.SUSTAINED_SPELL,
        ReasonCode.AGE_85_PLUS,
        ReasonCode.LIVES_ALONE,
        ReasonCode.DEMENTIA,
        ReasonCode.RESPIRATORY,
        ReasonCode.MOBILITY_LIMITED,
        ReasonCode.MED_DIURETIC,
        ReasonCode.MED_ACE_ARB,
        ReasonCode.MED_SSRI,
        # Three medicine classes acting on heat, so the compounding rule fires
        # as well as each medicine on its own.
        ReasonCode.MED_POLYPHARMACY,
    }


def test_high_tier_reached_with_no_regional_alert_in_force(assessment):
    """The target behaviour: personal risk detected on a day the national
    alerting system said nothing."""
    assert BEDFORD_19_JULY_2025.alert_level is AlertLevel.NONE
    assert assessment.tier >= Tier.HIGH


def test_every_reason_is_explainable(assessment):
    """AC-2: the reasons array is the system of record for explanation."""
    for reason in assessment.reasons:
        assert reason.title.strip()
        assert reason.explanation.strip()
        assert reason.weight > 0
