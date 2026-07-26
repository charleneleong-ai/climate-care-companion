class LearnedIndoor:
    """Track B. A fitted replacement for the FR-11 analytic indoor model, which is
    the dominant error term at plus or minus 3 to 5 degrees.

    Blocked on data that does not exist yet: this needs paired sensor readings and
    outdoor observations. The analytic form in packages/exposure stays the baseline
    until then, and a self-reported hot bedroom closes part of the gap today.
    """

    def estimate(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. Needs sensor data — deferred to v0.3.")
