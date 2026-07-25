from datetime import date, timedelta

import pytest
from contracts import AlertLevel, ExposureFeatures, ExposureSource
from core.corpus import Corpus
from core.scoring import RiskScorer


@pytest.fixture(scope="session")
def corpus() -> Corpus:
    return Corpus.load()


@pytest.fixture(scope="session")
def scorer(corpus) -> RiskScorer:
    return RiskScorer(corpus)


@pytest.fixture(scope="session")
def benign_season() -> list[ExposureFeatures]:
    """92 days of unremarkable English summer weather.

    Nothing here should alarm anyone. If the system raises a tier on any of these
    days it is crying wolf, and a caregiver who is warned about nothing stops
    reading the warnings.
    """
    start = date(2025, 6, 1)
    return [
        ExposureFeatures(
            date=start + timedelta(days=i),
            overnight_min=12.0,
            peak_apparent=19.0,
            peak_air=19.0,
            hours_above_26=0,
            indoor_night_est=19.5,
            indoor_day_est=21.0,
            spell_day=0,
            alert_level=AlertLevel.NONE,
            source=ExposureSource.FIXTURE,
        )
        for i in range(92)
    ]
