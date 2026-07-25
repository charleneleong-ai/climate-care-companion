from collections.abc import Sequence

from predictors.base import EpisodeForecast

EPISODE_THRESHOLD = 24.0
"""UKHSA episode definition, matching the EPISODES data in the national view."""


class ThresholdHeatwave:
    """Deterministic baseline. Ships green so the chain works from hour one.

    EnsembleHeatwave upgrades this in place behind the same Protocol. That is the
    mitigation for the largest schedule risk in the build: if the probabilistic
    model does not land, the lead-time story becomes deterministic rather than
    absent.
    """

    def __init__(self, threshold: float = EPISODE_THRESHOLD) -> None:
        self.threshold = threshold

    def forecast(
        self, daily_peaks: Sequence[float], horizon_days: int
    ) -> EpisodeForecast:
        window = list(daily_peaks[:horizon_days])
        qualifying = [i for i, peak in enumerate(window) if peak >= self.threshold]
        if not qualifying:
            return EpisodeForecast(
                horizon_days=horizon_days,
                p_onset=0.0,
                expected_peak=max(window, default=0.0),
                expected_duration_days=0,
                ensemble_spread=0.0,
                lead_time_hours=0,
            )
        return EpisodeForecast(
            horizon_days=horizon_days,
            p_onset=1.0,
            expected_peak=max(window),
            expected_duration_days=len(qualifying),
            ensemble_spread=0.0,
            lead_time_hours=qualifying[0] * 24,
        )


class EnsembleHeatwave:
    """Track B. P(onset) from the fraction of ICON/GFS/ECMWF members over threshold."""

    def forecast(
        self, daily_peaks: Sequence[float], horizon_days: int
    ) -> EpisodeForecast:
        raise NotImplementedError(
            "Track B owns this. Fetch the Open-Meteo ensemble endpoint, compute "
            "p_onset as the member fraction clearing EPISODE_THRESHOLD, and report "
            "ensemble_spread as the inter-member standard deviation of peak. "
            "SC-7: trigger preparation at a deliberately low p_onset and publish "
            "the false-positive rate from the backtest alongside it."
        )
