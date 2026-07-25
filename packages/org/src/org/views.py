class CouncilView:
    """Track B. Tier distribution by ward, tomorrow's rank_visits output, and the
    current coverage_gap. Answers: where do I send people tomorrow.

    A pure query over the assessment table. No new persistence (AC-4).
    """

    def render(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 8.")


class HospitalView:
    """Track B. Surge forecast: EpisodeForecast x cohort vulnerability distribution
    over the predictor's 14-day horizon, with ensemble spread carried through as a
    confidence band. Answers: how many beds, and when.

    Demonstrator only. This is expert-judgement weighting projected forward, not an
    epidemiological model — it shows shape and timing, never a number to staff
    against, and must be labelled as such wherever displayed.
    """

    def render(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 8.")


class CareHomeView:
    """Track B. Per-resident board sorted by tier, with the reason codes that put
    each resident there. Answers: which of my forty residents tonight.

    The sharpest of the three. Care homes already sit inside the UKHSA cascade and
    receive the alerts, yet held 677 of the 1,504 heat-associated deaths in England
    in summer 2025. The failure is not that the alert fails to arrive — it is that
    a building-level alert cannot say which resident is at risk. That gap is
    resolution, not distribution.
    """

    def render(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 8.")
