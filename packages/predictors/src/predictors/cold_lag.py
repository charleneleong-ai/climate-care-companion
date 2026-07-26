class ColdLagTracker:
    """Track B. Cold mortality lags the cold spell by 1 to 2 weeks (spec section 12),
    so an alerting-shaped design mistimes it. Cold requires tracking, not alerting —
    which is a design change, not a threshold change."""

    def track(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("Track B owns this. Deferred to v0.4 — see spec section 12.")
