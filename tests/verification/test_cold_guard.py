"""COLD_GUARD: the documented deviation from spec 8.1.

Suppressing a rule is dangerous — it trades a false positive for the risk of a
false negative, and SC-7 says false negatives are the dominant safety risk. These
assert the trade lands the right way: silent on a mild summer day, loud in genuine
cold.
"""

from datetime import date

import pytest
from contracts import AlertLevel, ExposureFeatures, ExposureSource, ReasonCode, Tier
from core.rules import HEATING_DAY_MAX
from core.vulnerability import VulnerabilityScorer
from exposure.indoor import IndoorModel
from persons.loader import PersonaLoader

COLD_CODES = {
    ReasonCode.INDOOR_BELOW_18,
    ReasonCode.INDOOR_BELOW_16,
    ReasonCode.INDOOR_BELOW_12,
}


def weather(night: float, day: float, offset: float = 0.5) -> ExposureFeatures:
    """Indoor figures derived from the model, never asserted."""
    model = IndoorModel()
    return ExposureFeatures(
        date=date(2025, 1, 15), overnight_min=night, peak_apparent=day, peak_air=day,
        hours_above_26=0,
        indoor_night_est=model.night(night, day, offset),
        indoor_day_est=model.day(night, day, offset),
        spell_day=0, alert_level=AlertLevel.NONE, source=ExposureSource.FIXTURE,
    )


def fired(scorer, exposure) -> set[ReasonCode]:
    profile = VulnerabilityScorer().profile(PersonaLoader().load()["margaret"])
    return {r.code for r in scorer.assess(exposure, profile).reasons} & COLD_CODES


@pytest.mark.parametrize(
    "night,day",
    [(12.0, 19.0), (11.0, 18.5), (14.0, 22.0)],
    ids=["mild-june", "cool-june", "warm-may"],
)
def test_no_cold_code_fires_on_a_mild_summer_day(scorer, night, day):
    """The modelled indoor figure dips below 18 on days nobody would call cold."""
    assert fired(scorer, weather(night, day)) == set()


@pytest.mark.parametrize(
    "night,day,expected",
    [(2.0, 7.0, ReasonCode.INDOOR_BELOW_12),
     (8.0, 15.0, ReasonCode.INDOOR_BELOW_16),
     (14.0, 17.5, ReasonCode.INDOOR_BELOW_18)],
    ids=["freezing", "cold", "chilly"],
)
def test_cold_codes_still_fire_in_genuine_cold(scorer, night, day, expected):
    """The guard must not have bought quiet summers at the cost of missing winter.

    The bands are lower than intuition suggests because FR-11 has no heating term:
    it models an unheated dwelling, so indoor tracks outdoor down. That is the
    right conservative assumption for a fuel-poor household and the wrong one for
    a heated home — see the note on Place.heating_affordable in docs/deviations.md.
    """
    assert expected in fired(scorer, weather(night, day))


def test_the_guard_threshold_is_a_plausible_heating_day():
    assert HEATING_DAY_MAX == 18.0


def test_an_unheated_home_on_a_cold_day_still_reaches_a_tier(scorer):
    """End to end: the guard suppresses an artefact, not a real cold risk."""
    doris = PersonaLoader().load()["doris"]
    assessment = scorer.assess(weather(2.0, 7.0), VulnerabilityScorer().profile(doris))
    assert assessment.tier >= Tier.HIGH
