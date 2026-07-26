from dataclasses import replace

from contracts import ExposureFeatures, ExposureSource, SelfReport


class IndoorModel:
    """FR-11 indoor temperature estimation.

    Modelled, not measured — label as modelled wherever displayed (SC-5). This is
    the dominant error term in the whole system at plus or minus 3 to 5 degrees.
    A bedroom sensor replaces it in v0.3; apply_self_report closes part of the gap
    today by asking the person directly.
    """

    SELF_REPORT_HOT_OFFSET = 1.5
    """Bounded. A subjective answer nudges the estimate; it never replaces it.
    An unbounded correction would let one yes/no answer dominate the model."""

    def __init__(self, self_report_offset: float = SELF_REPORT_HOT_OFFSET) -> None:
        self.self_report_offset = self_report_offset

    @staticmethod
    def night(outdoor_night_min: float, outdoor_day_max: float, dwelling_offset: float) -> float:
        return 0.6 * outdoor_night_min + 0.4 * outdoor_day_max + dwelling_offset

    @staticmethod
    def day(outdoor_night_min: float, outdoor_day_max: float, dwelling_offset: float) -> float:
        return 0.3 * outdoor_night_min + 0.55 * outdoor_day_max + dwelling_offset + 2

    def apply_self_report(self, features: ExposureFeatures, report: SelfReport) -> ExposureFeatures:
        """Correct the modelled estimate with what the person actually said.

        Red flags and no-answer are NOT handled here. They escalate at L4 and never
        enter risk fusion — the weather has not become more dangerous because a
        phone went unanswered, but what to do about it has (spec section 6).
        """
        if not report.answered or report.bedroom_feels_hot is not True:
            return features
        return replace(
            features,
            indoor_night_est=features.indoor_night_est + self.self_report_offset,
            source=ExposureSource.SELF_REPORT,
        )
