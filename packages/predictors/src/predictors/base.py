from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EpisodeForecast:
    horizon_days: int
    p_onset: float
    """P(episode threshold met). Deterministic predictors emit 0.0 or 1.0."""
    expected_peak: float
    expected_duration_days: int
    ensemble_spread: float
    """Model disagreement, i.e. confidence. Zero for a deterministic predictor."""
    lead_time_hours: int
    """The number a council actually acts on. Opening a cool space takes roughly
    72 hours, so a probability at day 5 is worth more than certainty at day 0."""


@runtime_checkable
class Predictor(Protocol):
    """The L1.5 seam.

    L3 never imports this package. Predictors produce ExposureFeatures and
    EpisodeForecast; the scoring core sees only the dataclasses. The seam holds in
    the import graph, not by convention.
    """

    def forecast(
        self, daily_peaks: Sequence[float], horizon_days: int
    ) -> EpisodeForecast: ...
