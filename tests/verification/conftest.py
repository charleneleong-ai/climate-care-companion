from datetime import date, timedelta

import pytest
from contracts import AlertLevel, ExposureFeatures, ExposureSource
from core.corpus import Corpus
from core.scoring import RiskScorer
from exposure.indoor import IndoorModel


@pytest.fixture(scope="session")
def corpus() -> Corpus:
    return Corpus.load()


@pytest.fixture(scope="session")
def scorer(corpus) -> RiskScorer:
    return RiskScorer(corpus)


BENIGN_NIGHT_MIN = 12.0
BENIGN_DAY_MAX = 19.0
MODEST_DWELLING_OFFSET = 0.5
"""A ground-floor, north-facing bungalow — the mildest dwelling in the lookup."""


@pytest.fixture(scope="session")
def benign_season() -> list[ExposureFeatures]:
    """92 days of unremarkable English summer weather.

    Nothing here should alarm anyone. If the system raises a tier on any of these
    days it is crying wolf, and a caregiver who is warned about nothing stops
    reading the warnings.

    The indoor figures are **derived from IndoorModel**, not asserted. An earlier
    version of this fixture hardcoded indoor_day_est=21.0, which is not what FR-11
    produces for this outdoor weather — it produces 16.55. That made the gate pass
    for the wrong reason and hid a genuine defect in the section 8.1 cold codes.
    A fixture that bypasses the model under test is not a test.
    """
    model = IndoorModel()
    start = date(2025, 6, 1)
    return [
        ExposureFeatures(
            date=start + timedelta(days=i),
            overnight_min=BENIGN_NIGHT_MIN,
            peak_apparent=BENIGN_DAY_MAX,
            peak_air=BENIGN_DAY_MAX,
            hours_above_26=0,
            indoor_night_est=model.night(
                BENIGN_NIGHT_MIN, BENIGN_DAY_MAX, MODEST_DWELLING_OFFSET
            ),
            indoor_day_est=model.day(
                BENIGN_NIGHT_MIN, BENIGN_DAY_MAX, MODEST_DWELLING_OFFSET
            ),
            spell_day=0,
            alert_level=AlertLevel.NONE,
            source=ExposureSource.FIXTURE,
        )
        for i in range(92)
    ]
