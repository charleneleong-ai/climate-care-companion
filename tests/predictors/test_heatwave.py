import pytest
from predictors.base import Predictor
from predictors.heatwave import EPISODE_THRESHOLD, EnsembleHeatwave, ThresholdHeatwave


@pytest.fixture(scope="module")
def predictor() -> ThresholdHeatwave:
    return ThresholdHeatwave()


def test_threshold_predictor_satisfies_the_protocol(predictor):
    assert isinstance(predictor, Predictor)


def test_onset_is_certain_when_every_day_clears_the_threshold(predictor):
    f = predictor.forecast([30.0, 30.0, 30.0], horizon_days=3)
    assert f.p_onset == 1.0
    assert f.expected_duration_days == 3
    assert f.ensemble_spread == 0.0  # deterministic: no disagreement to report


def test_no_onset_when_nothing_clears_the_threshold(predictor):
    f = predictor.forecast([15.0, 16.0, 15.0], horizon_days=3)
    assert f.p_onset == 0.0
    assert f.lead_time_hours == 0


def test_lead_time_counts_hours_to_the_first_qualifying_day(predictor):
    """The number a council acts on: three clear days ahead of onset is 72 hours,
    which is roughly what opening a cool space requires."""
    f = predictor.forecast([15.0, 15.0, 15.0, 30.0], horizon_days=4)
    assert f.p_onset == 1.0
    assert f.lead_time_hours == 72


@pytest.mark.parametrize("horizon", [1, 7, 14])
def test_forecast_never_reads_beyond_its_horizon(predictor, horizon):
    f = predictor.forecast([30.0] * 20, horizon_days=horizon)
    assert f.horizon_days == horizon
    assert f.expected_duration_days <= horizon


def test_empty_forecast_does_not_raise(predictor):
    f = predictor.forecast([], horizon_days=7)
    assert f.p_onset == 0.0
    assert f.expected_peak == 0.0


def test_threshold_is_configurable_without_editing_the_module(predictor):
    strict = ThresholdHeatwave(threshold=30.0)
    peaks = [25.0, 25.0]
    assert predictor.forecast(peaks, horizon_days=2).p_onset == 1.0
    assert strict.forecast(peaks, horizon_days=2).p_onset == 0.0


def test_ensemble_predictor_is_an_unclaimed_stub():
    with pytest.raises(NotImplementedError, match="Track B"):
        EnsembleHeatwave().forecast([30.0], horizon_days=1)
