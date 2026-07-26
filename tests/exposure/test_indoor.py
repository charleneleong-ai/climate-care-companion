from datetime import date

import pytest
from contracts import AlertLevel, DateRange, ExposureFeatures, ExposureSource, SelfReport
from exposure.indoor import IndoorModel
from exposure.normalise import ExposureNormaliser

BEDFORD = ExposureFeatures(
    date=date(2025, 7, 19),
    overnight_min=17.0,
    peak_apparent=29.0,
    peak_air=29.0,
    hours_above_26=7,
    indoor_night_est=24.6,
    indoor_day_est=25.85,
    spell_day=3,
    alert_level=AlertLevel.NONE,
    source=ExposureSource.ARCHIVE,
)
WINDOW = DateRange(date(2025, 7, 19), date(2025, 7, 20))


@pytest.fixture(scope="module")
def model() -> IndoorModel:
    return IndoorModel()


@pytest.fixture(scope="module")
def normaliser() -> ExposureNormaliser:
    return ExposureNormaliser()


def test_indoor_night_matches_the_spec_8_6_worked_example(model):
    assert model.night(17.0, 29.0, 2.8) == pytest.approx(24.6)


def test_indoor_day_matches_fr_11(model):
    assert model.day(17.0, 29.0, 2.8) == pytest.approx(25.85)


def test_overnight_minimum_uses_the_2200_to_0700_window_only(normaliser):
    """FR-07. The 15:00 low must be ignored; only 22:00-07:00 counts."""
    hourly = {h: 25.0 for h in range(24)}
    hourly[15] = 5.0  # decoy, outside the window
    hourly[3] = 18.0  # the real overnight minimum
    assert normaliser.overnight_minimum(hourly) == 18.0


def test_overnight_minimum_raises_when_the_window_is_empty(normaliser):
    with pytest.raises(ValueError, match="22:00"):
        normaliser.overnight_minimum({12: 20.0})


@pytest.mark.parametrize(
    "peaks,expected",
    [([25.0, 25.0, 25.0], 3), ([25.0, 20.0, 25.0], 1), ([], 0), ([20.0, 20.0], 0)],
)
def test_spell_day_counts_consecutive_days_only(normaliser, peaks, expected):
    """FR-09. A break in the spell resets the count."""
    assert normaliser.spell_day(peaks, threshold=24.0) == expected


def test_hours_above_counts_the_whole_day(normaliser):
    hourly = {h: 27.0 if h in (12, 13, 14) else 20.0 for h in range(24)}
    assert normaliser.hours_above(hourly, threshold=26.0) == 3


def test_self_report_of_a_hot_bedroom_raises_the_indoor_estimate(model):
    """Spec section 6: a cheap partial substitute for the v0.3 sensor."""
    after = model.apply_self_report(
        BEDFORD,
        SelfReport(person_id="doris", window=WINDOW, answered=True, bedroom_feels_hot=True),
    )
    assert after.indoor_night_est > BEDFORD.indoor_night_est
    assert after.source is ExposureSource.SELF_REPORT
    assert BEDFORD.indoor_night_est == 24.6, "input must not be mutated"


def test_self_report_correction_is_bounded(model):
    after = model.apply_self_report(
        BEDFORD,
        SelfReport(person_id="d", window=WINDOW, answered=True, bedroom_feels_hot=True),
    )
    assert after.indoor_night_est - BEDFORD.indoor_night_est <= 2.0


@pytest.mark.parametrize(
    "report",
    [
        SelfReport(person_id="d", window=WINDOW, answered=False),
        SelfReport(person_id="d", window=WINDOW, answered=True, bedroom_feels_hot=False),
        SelfReport(person_id="d", window=WINDOW, answered=True, bedroom_feels_hot=None),
    ],
    ids=["no_answer", "said_no", "did_not_say"],
)
def test_exposure_untouched_unless_the_person_said_yes(model, report):
    assert model.apply_self_report(BEDFORD, report) == BEDFORD
