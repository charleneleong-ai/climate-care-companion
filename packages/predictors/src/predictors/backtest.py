class SeasonBacktest:
    """Track B. Replay summer 2025 via the Open-Meteo archive.

    The headline question: would the model have flagged Episode 4 — 17 to 19 July
    2025, where UKHSA issued no alert in any region and an estimated 146 people
    died — at 72 hours or more of lead time? Falsifiable, and the strongest claim
    the project can make.
    """

    def run(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. See spec section 5.")
