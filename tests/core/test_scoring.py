from datetime import date

import pytest
from contracts import (
    AlertLevel,
    ExposureFeatures,
    ExposureSource,
    ReasonCode,
    Tier,
    VulnerabilityProfile,
)
from core.corpus import Corpus
from core.scoring import RiskScorer


@pytest.fixture(scope="module")
def scorer() -> RiskScorer:
    return RiskScorer(Corpus.load())


def exposure(**kw) -> ExposureFeatures:
    base = dict(date=date(2025, 7, 19), overnight_min=12.0, peak_apparent=18.0,
                peak_air=18.0, hours_above_26=0, indoor_night_est=19.0,
                indoor_day_est=21.0, spell_day=0, alert_level=AlertLevel.NOT_CHECKED,
                source=ExposureSource.FIXTURE)
    return ExposureFeatures(**(base | kw))


def vuln(score: int) -> VulnerabilityProfile:
    return VulnerabilityProfile(person_id="p", score=score, codes=())


@pytest.mark.parametrize(
    "risk,expected",
    [(0.0, Tier.LOW), (1.9, Tier.LOW), (2.0, Tier.ELEVATED), (4.9, Tier.ELEVATED),
     (5.0, Tier.HIGH), (8.9, Tier.HIGH), (9.0, Tier.SEVERE), (30.0, Tier.SEVERE)],
)
def test_tier_boundaries_per_spec_8_5(risk, expected):
    assert RiskScorer.tier_for(risk) is expected


def test_zero_exposure_returns_low_however_frail(scorer):
    """FR-18. The rule that stops frail people sitting permanently at Elevated."""
    a = scorer.assess(exposure(), vuln(score=30))
    assert a.exposure_score == 0
    assert a.tier is Tier.LOW
    assert a.risk_score == 0.0


def test_multiplier_is_one_plus_score_over_ten(scorer):
    a = scorer.assess(exposure(indoor_night_est=24.5), vuln(score=10))
    assert a.exposure_score == 1                 # BEDROOM_WARM
    assert a.risk_score == pytest.approx(2.0)    # 1 * (1 + 10/10)


@pytest.mark.parametrize(
    "indoor_night,expected_code",
    [(26.5, ReasonCode.BEDROOM_UNSAFE), (24.5, ReasonCode.BEDROOM_WARM)],
)
def test_bedroom_codes_are_mutually_exclusive(scorer, indoor_night, expected_code):
    codes = {r.code for r in scorer.assess(exposure(indoor_night_est=indoor_night),
                                           vuln(0)).reasons}
    assert codes & {ReasonCode.BEDROOM_UNSAFE, ReasonCode.BEDROOM_WARM} == {expected_code}


def test_reasons_carry_text_from_the_corpus_and_weight_from_the_rules(scorer):
    a = scorer.assess(exposure(indoor_night_est=24.5), vuln(0))
    reason = next(r for r in a.reasons if r.code is ReasonCode.BEDROOM_WARM)
    assert reason.title and reason.explanation
    assert reason.weight == 1


def test_vulnerability_codes_appear_in_the_reasons_array(scorer):
    v = VulnerabilityProfile(person_id="p", score=3, codes=(ReasonCode.AGE_85_PLUS,))
    codes = {r.code for r in scorer.assess(exposure(indoor_night_est=24.5), v).reasons}
    assert ReasonCode.AGE_85_PLUS in codes


def test_cold_codes_are_mutually_exclusive(scorer):
    codes = {r.code for r in scorer.assess(exposure(indoor_day_est=14.0), vuln(0)).reasons}
    cold = codes & {ReasonCode.INDOOR_BELOW_18, ReasonCode.INDOOR_BELOW_16,
                    ReasonCode.INDOOR_BELOW_12}
    assert cold == {ReasonCode.INDOOR_BELOW_16}


def test_assess_is_deterministic(scorer):
    e, v = exposure(indoor_night_est=24.5), vuln(10)
    assert scorer.assess(e, v) == scorer.assess(e, v)


def test_alert_level_does_not_influence_the_score(scorer):
    """The product argument: personal risk is computed whether or not a national
    alert is in force."""
    hot = dict(indoor_night_est=24.5, spell_day=3, peak_apparent=29.0)
    with_alert = scorer.assess(exposure(**hot, alert_level=AlertLevel.AMBER), vuln(10))
    without = scorer.assess(exposure(**hot, alert_level=AlertLevel.NONE), vuln(10))
    assert with_alert.risk_score == without.risk_score
